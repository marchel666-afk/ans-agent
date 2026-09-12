import threading,time,uuid
from dataclasses import dataclass,field
@dataclass
class Job:
 id:str=field(default_factory=lambda:str(uuid.uuid4()))
 session_id:str=""
 status:str="queued"
 created_at:float=field(default_factory=time.time)
 started_at:float|None=None
 finished_at:float|None=None
 result:dict=field(default_factory=dict)
 error:str|None=None
 cancel_requested:bool=False
class JobManager:
 def __init__(self): self.jobs={}; self.q=[]; self.cv=threading.Condition(); self.worker=threading.Thread(target=self._loop,daemon=True); self.worker.start()
 def submit(self,session_id,fn):
  j=Job(session_id=session_id)
  with self.cv:self.jobs[j.id]=j;self.q.append((j.id,fn));self.cv.notify()
  return j
 def get(self,jid): return self.jobs.get(jid)
 def cancel(self,jid):
  with self.cv:
   j=self.jobs.get(jid)
   if j and j.status in {"queued","running","waiting"}: j.cancel_requested=True; j.status="cancelled"; self.cv.notify_all(); return True
   return False
 def pop(self):
  with self.cv:
   while not self.q:self.cv.wait()
   jid,fn=self.q.pop(0); j=self.jobs[jid]
   if j.status=="queued": j.status="running";j.started_at=time.time();return j,fn
 def _loop(self):
  while True:
   j,fn=self.pop()
   try:
    if j.status=="cancelled": continue
    result=fn(j)
    if j.status!="cancelled": self.finish(j,result=result)
   except Exception as e:
    if j.status!="cancelled": self.finish(j,error=str(e))
 def finish(self,j,result=None,error=None):
  j.result=result or {};j.error=error;j.status="failed" if error else "completed";j.finished_at=time.time()
