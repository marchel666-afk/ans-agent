from .adapters import build_adapters, ProviderError
from .router import ModelRouter
from .types import AgentState, TaskMode
from .config import load_dotenv
from .tool_executor import ToolExecutor
from .tool_loop import ToolLoop

class Orchestrator:
    def __init__(self,router=None,workspace="./workspace",emit=None,approval=None,session_id=None):
        load_dotenv()
        self.router=router or ModelRouter()
        self.adapters=build_adapters()
        self.workspace=workspace
        self.emit=emit or (lambda *a,**k:None)
        self.approval=approval
        self.session_id=session_id

    def call(self,role,prompt,prefer_free=False,tools=False):
        profile=getattr(self,"profile",None)
        if profile:
            mapped={"planner":profile.planner,"architect":profile.planner,"reviewer":profile.reviewer,"researcher":profile.researcher,"judge":profile.judge}
            preferred=mapped.get(role)
            candidates=self.router.rank(role,requires_tools=tools,prefer_free=prefer_free)
            if preferred: candidates=sorted(candidates,key=lambda m: 0 if m.model==preferred or m.provider==preferred else 1)
        else:
            candidates=self.router.rank(role,requires_tools=tools,prefer_free=prefer_free)
        errors=[]
        for m in candidates:
            adapter=self.adapters.get(m.model) or self.adapters.get(m.provider)
            if not adapter:
                errors.append(f"{m.provider}: adapter unavailable"); continue
            try:
                started=__import__("time").time()
                result=adapter.complete(prompt,timeout=120)
                self.router.report_success(m)
                self.router.report_latency(m,__import__("time").time()-started,True)
                return result.text
            except ProviderError as e:
                self.router.report_failure(m); errors.append(str(e))
        raise ProviderError("No available provider: "+"; ".join(errors))

    def run(self,task,mode="agent",max_iterations=30):
        state=AgentState(task=task,mode=TaskMode(mode),max_iterations=max_iterations)
        profile=getattr(self,"profile",None)
        if profile: self.emit("profile.selected",profile.name,planner=profile.planner,executor=profile.executor,reviewer=profile.reviewer)
        plan_text=self.call("planner","Create an ordered implementation plan. Return one step per line.\n\nTASK:\n"+task)
        state.plan=[x.strip("- •0123456789.\t") for x in plan_text.splitlines() if x.strip()]
        if mode=="chat": return {"status":"completed","plan":[],"output":plan_text,"iterations":0}
        while state.plan and state.iteration<state.max_iterations:
            step=state.plan[0]; state.iteration+=1
            self.emit("step.started",step,iteration=state.iteration)
            try:
                candidates=self.router.rank("executor",requires_tools=True)
                if not candidates: raise ProviderError("No executor model available")
                m=candidates[0]
                adapter=self.adapters.get(m.model) or self.adapters.get(m.provider)
                if not adapter: raise ProviderError("Executor adapter unavailable: "+m.provider)
                executor=ToolExecutor(self.workspace)
                loop=ToolLoop(adapter,executor,emit=self.emit,
                              approval=self.approval,session_id=self.session_id)
                job=getattr(self,"job",None)
                executor.job=job
                executor.manager=getattr(self,"job_manager",None)
                output=loop.run(f"TASK: {task}\nSTEP: {step}\nInspect the workspace and implement this step. Verify your changes.",max_steps=20)
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
                break
            else:
                state.plan.append(state.plan.pop(0))
        state.status="completed" if not state.plan else "max_iterations"
        return {"status":state.status,"plan":state.plan,"completed":state.completed,"observations":state.observations,"iterations":state.iteration}
