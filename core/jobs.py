import json,sqlite3,threading,time,uuid
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
 timeout_seconds:int=3600
 attempts:list=field(default_factory=list)

class JobManager:
 def record_tool(self,name,args):
  self.emit("tool.usage",name,tool=name)
 def __init__(self,db_path="data/jobs.db",emit=None):
  self.db_path=db_path;self.emit=emit or (lambda *a,**k:None);self.jobs={};self.q=[];self.cv=threading.Condition();self._init_db();self.worker=threading.Thread(target=self._loop,daemon=True);self.worker.start()
 def _db(self):
  c=sqlite3.connect(self.db_path);c.execute("PRAGMA journal_mode=WAL");return c
 def _init_db(self):
  import os;os.makedirs(os.path.dirname(self.db_path) or ".",exist_ok=True)
  with self._db() as c:
   c.execute("CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY,session_id TEXT,status TEXT,created REAL,started REAL,finished REAL,result TEXT,error TEXT,cancel INTEGER)")
   try:c.execute("ALTER TABLE jobs ADD COLUMN attempts TEXT DEFAULT '[]'")
   except sqlite3.OperationalError:pass
 def submit(self,session_id,fn,timeout_seconds=3600):
  j=Job(session_id=session_id,timeout_seconds=max(1,int(timeout_seconds)))
  with self._db() as c:c.execute("INSERT INTO jobs(id,session_id,status,created,started,finished,result,error,cancel,attempts) VALUES(?,?,?,?,?,?,?,?,?,?)",(j.id,j.session_id,j.status,j.created_at,None,None,"",None,0,"[]"))
  with self.cv:self.jobs[j.id]=j;self.q.append((j.id,fn));self.cv.notify()
  self.emit("job.created","Job queued",job_id=j.id);return j
 def get(self,jid):
  j=self.jobs.get(jid)
  if j:
   if j.status in {"queued","running","waiting"} and j.started_at and time.time()-j.started_at>j.timeout_seconds:
    j.status="failed";j.error=f"Job exceeded timeout of {j.timeout_seconds}s";j.finished_at=time.time();self._save(j);self.emit("job.timeout",j.error,job_id=j.id)
   return j
  with self._db() as c:r=c.execute("SELECT * FROM jobs WHERE id=?",(jid,)).fetchone()
  if not r:return None
  j=Job(r[0],r[1],r[2],r[3],r[4],r[5],json.loads(r[6] or "{}"),r[7],bool(r[8]))
  if len(r)>9:j.attempts=json.loads(r[9] or "[]")
  return j
 def _save(self,j):
  with self._db() as c:c.execute("UPDATE jobs SET status=?,started=?,finished=?,result=?,error=?,cancel=?,attempts=? WHERE id=?",(j.status,j.started_at,j.finished_at,json.dumps(j.result,ensure_ascii=False),j.error,int(j.cancel_requested),json.dumps(j.attempts,ensure_ascii=False),j.id))
 def cancel(self,jid):
  with self.cv:
   j=self.get(jid)
   if j and j.status in {"queued","running","waiting"}:j.cancel_requested=True;j.status="cancelled";self._save(j);self.cv.notify_all();self.emit("job.cancelled","Job cancelled",job_id=jid);return True
   return False
 def set_waiting(self,j):
  j.status="waiting";self._save(j);self.emit("job.waiting","Job waiting for approval",job_id=j.id)
 def set_running(self,j):
  j.status="running";self._save(j);self.emit("job.running","Job resumed",job_id=j.id)
 def _loop(self):
  while True:
   with self.cv:
    while not self.q:self.cv.wait()
    jid,fn=self.q.pop(0);j=self.jobs[jid]
   if j.status=="cancelled":continue
   j.status="running";j.started_at=time.time();self._save(j);self.emit("job.started","Job started",job_id=j.id)
   try:
    attempt={"number":len(j.attempts)+1,"started_at":time.time(),"status":"running"}
    j.attempts.append(attempt);self._save(j)
    result=fn(j)
    if time.time()-j.started_at>j.timeout_seconds:raise TimeoutError(f"Job exceeded timeout of {j.timeout_seconds}s")
    attempt.update({"status":"completed","finished_at":time.time()})
    if j.cancel_requested:j.status="cancelled";j.finished_at=time.time();self._save(j);self.emit("job.cancelled","Job cancelled",job_id=j.id)
    elif j.status!="cancelled":j.result=result or {};j.status="completed";j.finished_at=time.time();self._save(j);self.emit("job.completed","Job completed",job_id=j.id)
   except Exception as e:
    if j.attempts:j.attempts[-1].update({"status":"failed","finished_at":time.time(),"error":str(e)[:500]})
    j.error=str(e);j.status="failed";j.finished_at=time.time();self._save(j);self.emit("job.failed","Job failed",job_id=j.id,error=str(e))