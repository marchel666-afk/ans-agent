from .adapters import build_adapters, ProviderError
from .router import ModelRouter
from .types import AgentState, TaskMode
from .config import load_dotenv
from .tool_executor import ToolExecutor
from .tool_loop import ToolLoop
from .task_graph import TaskGraph
from .git_workspace import GitWorkspaceManager
from .memory import ProjectMemory
import subprocess, os

class Orchestrator:
    def __init__(self,router=None,workspace="./workspace",emit=None,approval=None,session_id=None):
        load_dotenv()
        self.router=router or ModelRouter()
        self.adapters=build_adapters()
        self.workspace=workspace
        self.emit=emit or (lambda *a,**k:None)
        self.approval=approval
        self.session_id=session_id
        self.memory=None

    def call(self,role,prompt,prefer_free=False,tools=False,policy="balanced",budget=None):
        profile=getattr(self,"profile",None)
        if profile:
            mapped={"planner":profile.planner,"architect":profile.planner,"reviewer":profile.reviewer,"researcher":profile.researcher,"judge":profile.judge}
            preferred=mapped.get(role)
            candidates=self.router.policy_rank(role,policy,requires_tools=tools,budget=budget)
            if preferred: candidates=sorted(candidates,key=lambda m: 0 if m.model==preferred or m.provider==preferred else 1)
        else:
            candidates=self.router.policy_rank(role,policy,requires_tools=tools,budget=budget)
        errors=[]
        for m in candidates:
            adapter=self.adapters.get(m.model) or self.adapters.get(m.provider)
            if not adapter:
                errors.append(f"{m.provider}: adapter unavailable"); continue
            try:
                self.emit("provider.selected",m.provider+"/"+m.model,role=role,policy=policy,budget=budget,score=self.router.score(m,role),estimated_cost=self.router.cost_estimate(m,4000,2000))
                started=__import__("time").time()
                result=adapter.complete(prompt,timeout=120,model=m.model,cwd=self.workspace)
                elapsed=__import__("time").time()-started
                self.router.report_success(m)
                self.router.report_latency(m,elapsed,True)
                self.router.record_task(m,role,True,elapsed)
                return result.text
            except Exception as e:
                error=str(e)[:180]
                elapsed=__import__("time").time()-started
                failure=self.router.report_failure(m,error=error)
                self.router.record_task(m,role,False,elapsed)
                errors.append(f"{m.provider}: {error}")
                self.emit("provider.failed",error,provider=m.provider,model=m.model,role=role,category=failure["category"],cooldown_seconds=failure["cooldown_seconds"])
        raise ProviderError("No available provider: "+"; ".join(errors))

    def run(self,task,mode="agent",max_iterations=30,policy="balanced",budget=None):
        original_task=task
        self.policy=policy
        self.budget=budget
        state=AgentState(task=task,mode=TaskMode(mode),max_iterations=max_iterations)
        if self.memory:
            context=self.memory.get_context()
            task="PROJECT MEMORY:\n"+context+"\n\nTASK:\n"+task
        profile=getattr(self,"profile",None)
        if profile: self.emit("profile.selected",profile.name,planner=profile.planner,executor=profile.executor,reviewer=profile.reviewer)
        plan_text=self.call("planner","Create an ordered implementation plan. Return one step per line.\n\nTASK:\n"+task)
        state.plan=[x.strip("- •0123456789.\t") for x in plan_text.splitlines() if x.strip()]
        graph=TaskGraph(state.plan)
        self.emit("task.graph",graph.snapshot())
        if mode=="chat": return {"status":"completed","plan":[],"output":plan_text,"iterations":0}
        if mode=="autopilot" and state.plan:
            return self._run_parallel_graph(task,state,graph)
        while state.plan and state.iteration<state.max_iterations:
            step=state.plan[0]; state.iteration+=1
            self.emit("step.started",step,iteration=state.iteration)
            try:
                policy=getattr(self,"policy","balanced")
                budget=getattr(self,"budget",None)
                candidates=self.router.policy_rank("executor",policy,requires_tools=True,budget=budget)
                if not candidates: raise ProviderError("No executor model available")
                executor=ToolExecutor(self.workspace)
                job=getattr(self,"job",None)
                executor.job=job
                executor.manager=getattr(self,"job_manager",None)
                output=None
                errors=[]
                job=getattr(self,"job",None)
                for attempt_number,m in enumerate(candidates,1):
                    adapter=self.adapters.get(m.model) or self.adapters.get(m.provider)
                    if not adapter:
                        errors.append(f"{m.provider}: adapter unavailable")
                        continue
                    attempt={"number":attempt_number,"provider":m.provider,"model":m.model,"role":"executor","step":step,"started_at":__import__("time").time(),"status":"running"}
                    if job is not None:
                        job.attempts.append(attempt)
                        manager=getattr(self,"job_manager",None)
                        if manager: manager._save(job)
                    started=__import__("time").time()
                    try:
                        self.emit("provider.selected",m.provider+"/"+m.model,role="executor",step=step,attempt=attempt_number,policy=policy,budget=budget,score=self.router.score(m,"executor"),estimated_cost=self.router.cost_estimate(m,4000,2000))
                        loop=ToolLoop(adapter,executor,emit=self.emit,
                                      approval=self.approval,session_id=self.session_id)
                        output=loop.run(f"TASK: {task}\nSTEP: {step}\nInspect the workspace and implement this step. Verify your changes.",max_steps=20)
                        elapsed=__import__("time").time()-started
                        self.router.report_success(m)
                        self.router.record_task(m,"executor",True,elapsed)
                        attempt.update({"status":"completed","finished_at":__import__("time").time()})
                        if manager: manager._save(job)
                        break
                    except Exception as e:
                        error=str(e)[:180]
                        failure=self.router.report_failure(m,error=error)
                        self.router.record_task(m,"executor",False,__import__("time").time()-started)
                        attempt.update({"status":"failed","finished_at":__import__("time").time(),"error":error,"category":failure["category"]})
                        if manager: manager._save(job)
                        errors.append(f"{m.provider}: {error}")
                        self.emit("provider.failed",error,provider=m.provider,model=m.model,role="executor",step=step,attempt=attempt_number,category=failure["category"],cooldown_seconds=failure["cooldown_seconds"])
                if output is None:
                    raise ProviderError("All executor providers failed: "+"; ".join(errors))
            except Exception as e:
                output="EXECUTOR ERROR: "+str(e)
            self.emit("executor.report",output,step=step)
            if output.startswith("APPROVAL_REQUIRED:"):
                state.status="approval_required"
                return {"status":state.status,"plan":state.plan,"completed":state.completed,"observations":state.observations,"iterations":state.iteration}
            review=self.call("reviewer",f"Task: {task}\nStep: {step}\nExecutor report:\n{output}\n\nReturn PASS or FAIL first, then concrete reasoning.")
            self.emit("review",review,step=step)
            state.observations.extend([f"STEP {state.iteration}: {step}",output,review])
            if review.strip().upper().startswith("PASS"):
                state.completed.append(step); state.plan.pop(0); self.emit("step.passed",step)
            elif mode=="agent":
                repair=self.call("fixer",f"Task: {task}\nStep: {step}\nReview failure:\n{review}\nExecutor report:\n{output}\nFix the issue and return a concise repair plan.",tools=False)
                self.emit("repair.requested",repair,step=step)
                state.plan.insert(0,step)
                if state.iteration>=state.max_iterations: break
            else:
                state.plan.append(state.plan.pop(0))
        if self.memory and state.completed:
            self.memory.remember_result(original_task, "\n".join(state.observations[-8:]))
        state.status="completed" if not state.plan else "max_iterations"
        return {"status":state.status,"plan":state.plan,"completed":state.completed,"observations":state.observations,"iterations":state.iteration}

    def _run_parallel_graph(self,task,state,graph,max_workers=3):
        import os
        git=GitWorkspaceManager(self.workspace) if os.path.exists(os.path.join(self.workspace,".git")) else None
        def execute(node):
            path=self.workspace; branch=None
            if git:
                w=git.create(node.id); path=w["path"]; branch=w["branch"]
            executor=ToolExecutor(path)
            candidates=self.router.rank("executor",requires_tools=True)
            if not candidates: raise ProviderError("No executor model available")
            output=None; errors=[]
            for m in candidates:
                adapter=self.adapters.get(m.model) or self.adapters.get(m.provider)
                if not adapter: continue
                try:
                    loop=ToolLoop(adapter,executor,emit=self.emit,approval=self.approval,session_id=self.session_id)
                    output=loop.run("TASK: "+task+"\nSTEP: "+node.title+"\nInspect the workspace and implement this step. Verify your changes.",max_steps=20)
                    self.router.report_success(m)
                    break
                except Exception as e:
                    self.router.report_failure(m); errors.append(f"{m.provider}: {str(e)[:160]}")
            if output is None: raise ProviderError("All executor providers failed: "+"; ".join(errors))
            if git and branch and not output.startswith("APPROVAL_REQUIRED:"):
                try: git.commit(path,"ANS: "+node.title[:60])
                except Exception as e: self.emit("commit.failed",{"node":node.id,"error":str(e)})
            return {"output":output,"branch":branch,"path":path}
        results=graph.run_parallel(execute,max_workers=max_workers)
        if git:
            for node in graph.nodes.values():
                item=results.get(node.id,{})
                branch=item.get("branch") if isinstance(item,dict) else None
                if branch:
                    check=git.can_merge(branch)
                    self.emit("merge.check",{"node":node.id,"branch":branch,"clean":check["clean"]})
                    if check["clean"]:
                        try:
                            git.merge(branch)
                            git.cleanup_merged()
                            self.emit("merge.completed",{"node":node.id,"branch":branch})
                        except Exception as e:
                            self.emit("merge.failed",{"node":node.id,"branch":branch,"error":str(e)})
        self.emit("task.graph.completed",graph.snapshot())
        return {"status":"completed" if all(n.status=="done" for n in graph.nodes.values()) else "partial","plan":[],"completed":[n.title for n in graph.nodes.values() if n.status=="done"],"observations":results,"iterations":state.iteration}

    def _verify_workspace(self):
        if not os.path.exists(os.path.join(self.workspace,".git")): return {"ok":True,"tests":"no git repo"}
        r=subprocess.run(["git","diff","--check"],cwd=self.workspace,text=True,capture_output=True)
        return {"ok":r.returncode==0,"tests":"git diff --check","output":r.stdout+r.stderr}
