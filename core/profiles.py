from dataclasses import dataclass,field
@dataclass
class AgentProfile:
 name:str
 planner:str="gpt"
 executor:str="claude-code"
 reviewer:str="gpt"
 researcher:str="gemini"
 judge:str="gpt"
 prefer_free:bool=False
 max_iterations:int=30
class ProfileRegistry:
 def __init__(self):
  self.items={
   "developer":AgentProfile("developer"),
   "game_developer":AgentProfile("game_developer",planner="gpt",executor="claude-code",reviewer="gemini",researcher="gemini"),
   "researcher":AgentProfile("researcher",planner="gemini",executor="claude-code",reviewer="gpt",researcher="gemini",prefer_free=True),
   "budget":AgentProfile("budget",planner="openrouter/free",executor="claude-code",reviewer="openrouter/free",researcher="openrouter/free",prefer_free=True),
  }
 def get(self,name): return self.items.get(name,self.items["developer"])
 def all(self): return [p.__dict__ for p in self.items.values()]
