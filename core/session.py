import uuid,time,sqlite3,json,os
from dataclasses import dataclass,field
@dataclass
class Session:
 id:str=field(default_factory=lambda:str(uuid.uuid4())); task:str=""; mode:str="agent"; events:list=field(default_factory=list); created_at:float=field(default_factory=time.time)
 def emit(self,kind,message,**data): self.events.append({"ts":time.time(),"kind":kind,"message":message,**data})
class SessionStore:
 def __init__(self,db_path=None):
  self.db_path=db_path or os.getenv("ANS_DB","./data/ans.db"); os.makedirs(os.path.dirname(os.path.abspath(self.db_path)),exist_ok=True); self._init()
 def _db(self):
  c=sqlite3.connect(self.db_path); c.row_factory=sqlite3.Row; return c
 def _init(self):
  with self._db() as c:
   c.execute("CREATE TABLE IF NOT EXISTS sessions(id TEXT PRIMARY KEY,task TEXT,mode TEXT,created_at REAL)")
   c.execute("CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY AUTOINCREMENT,session_id TEXT,ts REAL,kind TEXT,message TEXT,data TEXT)")
   c.execute("CREATE TABLE IF NOT EXISTS memories(id INTEGER PRIMARY KEY AUTOINCREMENT,project TEXT,key TEXT,value TEXT,updated_at REAL,UNIQUE(project,key))")
 def create(self,task,mode):
  s=Session(task=task,mode=mode)
  with self._db() as c:c.execute("INSERT INTO sessions VALUES(?,?,?,?)",(s.id,s.task,s.mode,s.created_at))
  return s
 def get(self,sid):
  with self._db() as c:
   r=c.execute("SELECT * FROM sessions WHERE id=?",(sid,)).fetchone()
   if not r:return None
   s=Session(id=r["id"],task=r["task"],mode=r["mode"],created_at=r["created_at"])
   for e in c.execute("SELECT ts,kind,message,data FROM events WHERE session_id=? ORDER BY id",(sid,)):
    s.events.append({"ts":e["ts"],"kind":e["kind"],"message":e["message"],**json.loads(e["data"] or "{}")})
   return s
 def emit(self,sid,kind,message,**data):
  with self._db() as c:c.execute("INSERT INTO events(session_id,ts,kind,message,data) VALUES(?,?,?,?,?)",(sid,time.time(),kind,message,json.dumps(data,ensure_ascii=False)))
 def save_memory(self,project,key,value):
  with self._db() as c:c.execute("INSERT INTO memories(project,key,value,updated_at) VALUES(?,?,?,?) ON CONFLICT(project,key) DO UPDATE SET value=excluded.value,updated_at=excluded.updated_at",(project,key,value,time.time()))
 def memories(self,project):
  with self._db() as c:return {r["key"]:r["value"] for r in c.execute("SELECT key,value FROM memories WHERE project=?",(project,))}
 def list(self):
  with self._db() as c: rows=c.execute("SELECT * FROM sessions ORDER BY created_at").fetchall()
  return [Session(id=r["id"],task=r["task"],mode=r["mode"],created_at=r["created_at"]) for r in rows]
