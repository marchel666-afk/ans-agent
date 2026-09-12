from .adapters import build_adapters, ProviderError
from .router import ModelRouter
from .types import AgentState, TaskMode
from .config import load_dotenv
from .tool_executor import ToolExecutor
from .tool_loop import ToolLoop

class Orchestrator:
    def __init__(self,router=None,workspace="./workspace",emit=None):
        load_dotenv(); self.router=router or ModelRouter(); self.adapters=build_adapters(); self.workspace=workspace; self.emit=emit or (lambda *a,**k:None)
    def call(self,role,prompt,prefer_free=False,tools=False):
        candidates=self.router.registry.for_role(role)
        if prefer_free: candidates=[m for m in candidates if m.free] or candidates
        if tools: candidates=[m for m in candidates if m.tool_capable] or candidates
        errors=[]
        for m in candidates:
            adapter=self.adapters.get(m.model) or self.adapters.get(m.provider)
            if not adapter: errors.append(f"{m.provider}: adapter unavailable"); continue
            try:\n                result=adapter.complete(prompt); self.router.report_success(m); return result.text
            except ProviderError as e: self.router.report_failure(m); errors.append(str(e))
        raise ProviderError("No available provider: "+"; ".join(errors))
    def run(self,task,mode="agent",max_iterations=30):
        state=AgentState(task=task,mode=TaskMode(mode),max_iterations=max_iterations)
        plan_text=self.call("planner","Create an ordered implementation plan. Return one step per line.\n\nTASK:\n"+task)
        state.plan=[x.strip("- •0123456789.\t") for x in plan_text.splitlines() if x.strip()]
        if mode=="chat": return {"status":"completed","plan":[],"output":plan_text,"iterations":0}
        while state.plan and state.iteration<state.max_iterations:
            step=state.plan[0]; state.iteration+=1; self.emit("step.started",step,iteration=state.iteration)
            try:
                adapter=self.adapters.get("claude-code") or self.adapters.get("anthropic")
                if not adapter: raise ProviderError("Claude Code adapter unavailable")
                loop=ToolLoop(adapter,ToolExecutor(self.workspace),emit=self.emit)
                output=loop.run(f"TASK: {task}\nSTEP: {step}\nInspect the workspace and implement this step. Verify your changes.",max_steps=20)
            except Exception as e: output="EXECUTOR ERROR: "+str(e)
            self.emit("executor.report",output,step=step)
            review=self.call("reviewer",f"Task: {task}\nStep: {step}\nExecutor report:\n{output}\n\nReturn PASS or FAIL first, then concrete reasoning.")
            self.emit("review",review,step=step)
            state.observations.extend([f"STEP {state.iteration}: {step}",output,review])
            if review.strip().upper().startswith("PASS"):
                state.completed.append(step); state.plan.pop(0); self.emit("step.passed",step)
            elif mode=="agent": break
            else: state.plan.append(state.plan.pop(0))
        state.status="completed" if not state.plan else "max_iterations"
        return {"status":state.status,"plan":state.plan,"completed":state.completed,"observations":state.observations,"iterations":state.iteration}
