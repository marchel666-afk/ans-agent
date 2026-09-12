class MultiAgent:
 def __init__(self,orch): self.orch=orch
 def run(self,task):
  plan=self.orch.call("planner","Break this task into implementation, research, testing and review responsibilities.\n"+task)
  research=self.orch.call("researcher","Research useful constraints and pitfalls for:\n"+task)
  implementation=self.orch.call("architect","Design the implementation using this research:\n"+research+"\nTASK:\n"+task)
  review=self.orch.call("reviewer","Review this plan for correctness and missing risks:\n"+implementation)
  return {"plan":plan,"research":research,"implementation":implementation,"review":review}
