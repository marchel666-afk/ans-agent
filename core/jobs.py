import json,sqlite3,threading,time,uuid
from dataclasses import dataclass,field
@dataclass
class Job:
 id:str=field(default_factory=lambda:str(uuid.uuid4())); session_id:str=""; status:str="queued"; created_at:float=field(default_factory=time.time); started_at:float|None=None; finished_at:float|None=None; result:dict=field(default_factory=dict); error:str|None=None; cancel_requested:bool=False
class JobManager:
 def __init__(self,db_path="data/jobs.db",emit=None):
  self.db_path=db_path;self.emit=emit or (lambda *a,**k:None);self.jobs={};self.q=[];self.cv=threading.Condition();self._init_db();self.worker=threading.Thread(target=self._loop,daemon=True);self.worker.start()
 def _db(self):
  c=sqlite3.connect(self.db_path);c.execute("PRAGMA journal_mode=WAL");return c
 def _init_db(self):
  import os;os.makedirs(os.path.dirname(self.db_path) or ".",exist_ok=True)
  with self._db() as c:c.execute("CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY,session_id TEXT,status TEXT,created REAL,started REAL,finished REAL,result TEXT,error TEXT,cancel INTEGER)")
 def submit(self,session_id,fn):
  j=Job(session_id=session_id)
  with self._db() as c:c.execute("INSERT INTO jobs VALUES(?,?,?,?,?,?,?,?,?)",(j.id,j.session_id,j.status,j.created_at,None,None,"",None,0))
  with self.cv:self.jobs[j.id]=j;self.q.append((j.id,fn));self.cv.notify()
  self.emit("job.created","Job queued",job_id=j.id);return j
 def get(self,jid):
  j=self.jobs.get(jid)
  if j:return j
  with self._db() as c:r=c.execute("SELECT * FROM jobs WHERE id=?",(jid,)).fetchone()
  if not r:return None
  return Job(r[0],r[1],r[2],r[3],r[4],r[5],json.loads(r[6] or "{}"),r[7],bool(r[8]))
 def _save(self,j):
  with self._db() as c:c.execute("UPDATE jobs SET status=?,started=?,finished=?,result=?,error=?,cancel=? WHERE id=?",(j.status,j.started_at,j.finished_at,json.dumps(j.result,ensure_ascii=False),j.error,int(j.cancel_requested),j.id))
 def cancel(self,jid):
  with self.cv:
   j=self.get(jid)
   if j and j.status in {"queued","running","waiting"}:j.cancel_requested=True;j.status="cancelled";self._save(j);self.cv.notify_all();self.emit("job.cancelled","Job cancelled",job_id=jid);return True
   return False
 def set_waiting(self,j):
  j.status="waiting";self._save(j);self.emit("job.waiting","Job waiting for approval",job_id=j.id)
 def _loop(self):
  while True:
   with self.cv:
    while not self.q:self.cv.wait()
    jid,fn=self.q.pop(0);j=self.jobs[jid]
   if j.status=="cancelled":continue
   j.status="running";j.started_at=time.time();self._save(j);self.emit("job.started","Job started",job_id=j.id)
   try:
    result=fn(j)
    if j.status!="cancelled":j.result=result or {};j.status="completed";j.finished_at=time.time();self._save(j);self.emit("job.completed","Job completed",job_id=j.id)
   except Exception as e:
    j.error=str(e);j.status="failed";j.finished_at=time.time();self._save(j);self.emit("job.failed","Job failed",job_id=j.id,error=str(e))
