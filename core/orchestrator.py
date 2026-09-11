from .adapters import build_adapters, ProviderError
from .router import ModelRouter
from .types import AgentState, TaskMode
from .loop import AgentLoop, StepResult

class Orchestrator:
    def __init__(self,router=None): self.router=router or ModelRouter(); self.adapters=build_adapters()
    def call(self,role,prompt,prefer_free=False,tools=False):
        candidates=self.router.registry.for_role(role)
        if prefer_free: candidates=[m for m in candidates if m.free] or candidates
        if tools: candidates=[m for m in candidates if m.tool_capable] or candidates
        errors=[]
        for m in candidates:
            adapter=self.adapters.get(m.model) or self.adapters.get(m.provider)
            if not adapter: errors.append(f"{m.provider}: adapter unavailable"); continue
            try: return adapter.complete(prompt).text
            except ProviderError as e: errors.append(str(e))
        raise ProviderError("No available provider: "+"; ".join(errors))

    def run(self,task,mode="agent",max_iterations=30):
        state=AgentState(task=task,mode=TaskMode(mode),max_iterations=max_iterations)
        plan_text=self.call("planner","Create an ordered implementation plan for this task. Return one step per line, no numbering required.\n\nTASK:\n"+task,prefer_free=False)
        state.plan=[x.strip("- •0123456789.\t") for x in plan_text.splitlines() if x.strip()]
        if mode=="chat": return {"status":"completed","plan":[],"output":plan_text,"iterations":0}
        while state.plan and state.iteration<state.max_iterations:
            step=state.plan[0]; state.iteration+=1
            prompt=f"TASK: {task}\nCURRENT STEP: {step}\nWork on the project using available tools. Return a concise report of actions and result."
            try: output=self.call("executor",prompt,tools=True)
            except ProviderError as e: output=str(e)
            review=self.call("reviewer",f"Task: {task}\nStep: {step}\nExecutor report:\n{output}\n\nDecide PASS or FAIL and explain briefly.")
            state.observations.extend([output,review])
            if review.strip().upper().startswith("PASS"):
                state.completed.append(step); state.plan.pop(0)
            else:
                state.plan.append(state.plan.pop(0))
                if mode=="agent": break
        state.status="completed" if not state.plan else "max_iterations"
        return {"status":state.status,"plan":state.plan,"completed":state.completed,"observations":state.observations,"iterations":state.iteration}
