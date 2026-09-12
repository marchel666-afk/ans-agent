import threading, time, uuid
from dataclasses import dataclass, field
@dataclass
class Job:
 id:str=field(default_factory=lambda:str(uuid.uuid4())); session_id:str=""; status:str="queued"; created_at:float=field(default_factory=time.time); started_at:float|None=None; finished_at:float|None=None; result:dict=field(default_factory=dict); error:str|None=None
class JobManager:
 def __init__(self): self.jobs={}; self.q=[]; self.cv=threading.Condition()
 def submit(self,session_id):
  j=Job(session_id=session_id)
  with self.cv:self.jobs[j.id]=j;self.q.append(j.id);self.cv.notify()
  return j
 def get(self,jid): return self.jobs.get(jid)
 def cancel(self,jid):
  with self.cv:
   j=self.jobs.get(jid)
   if j and j.status in {"queued","running","waiting"}: j.status="cancelled"; self.cv.notify_all(); return True
   return False
 def pop(self):
  with self.cv:
   while not self.q:self.cv.wait()
   jid=self.q.pop(0); j=self.jobs[jid]
   if j.status=="queued":j.status="running";j.started_at=time.time();return j
 def finish(self,j,result=None,error=None):
  j.result=result or {};j.error=error;j.status="failed" if error else "completed";j.finished_at=time.time()
