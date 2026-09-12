import os
class ProjectMemory:
 def __init__(self,store,project="default"): self.store=store; self.project=project
 def get_context(self):
  m=self.store.memories(self.project)
  if not m:return "No stored project memory."
  return "\n".join(f"- {k}: {v}" for k,v in m.items())
 def remember(self,key,value): self.store.save_memory(self.project,key,value)

class AgentMemory:
 def search_relevant(self,task,limit=10):
  try: return self.store.memories(self.project)
  except Exception: return {}
 def put(self,key,value):
  self.store.save_memory(self.project,key,value)
