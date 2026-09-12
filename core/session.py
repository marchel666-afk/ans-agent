import uuid, time
from dataclasses import dataclass, field
@dataclass
class Session:
    id:str=field(default_factory=lambda:str(uuid.uuid4()))
    task:str=""
    mode:str="agent"
    events:list=field(default_factory=list)
    created_at:float=field(default_factory=time.time)
    def emit(self,kind,message,**data): self.events.append({"ts":time.time(),"kind":kind,"message":message,**data})
class SessionStore:
    def __init__(self): self.sessions={}
    def create(self,task,mode):
        s=Session(task=task,mode=mode); self.sessions[s.id]=s; return s
    def get(self,sid): return self.sessions.get(sid)
    def list(self): return list(self.sessions.values())
