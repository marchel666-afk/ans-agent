import os,time,sqlite3
from dataclasses import dataclass
from .registry import ModelRegistry
from .types import ModelCandidate
@dataclass
class RouteDecision:
 candidate: ModelCandidate
 reason: str
class ModelRouter:
 def __init__(self,registry=None):
  self.registry=registry or ModelRegistry.default(); self.failures={}
  self.db=os.getenv("ANS_ROUTER_DB","./data/router_stats.db"); os.makedirs(os.path.dirname(self.db) or ".",exist_ok=True)
  self.stats={}; self.benchmarks={}
  with sqlite3.connect(self.db) as c:
   c.execute("CREATE TABLE IF NOT EXISTS model_stats(model TEXT PRIMARY KEY, ok INTEGER DEFAULT 0, fail INTEGER DEFAULT 0, latency REAL DEFAULT 0)")
   for model,ok,fail,lat in c.execute("SELECT model,ok,fail,latency FROM model_stats"): self.stats[model]={"ok":ok,"fail":fail,"latency":lat}
 def _persist(self,m):
  s=self.stats[m.model]
  with sqlite3.connect(self.db) as c: c.execute("INSERT INTO model_stats(model,ok,fail,latency) VALUES(?,?,?,?) ON CONFLICT(model) DO UPDATE SET ok=excluded.ok,fail=excluded.fail,latency=excluded.latency",(m.model,s["ok"],s["fail"],s["latency"]))
 def discover_openrouter(self, limit=100):
  import json, urllib.request
  key=os.getenv("OPENROUTER_API_KEY")
  if not key: return {"ok":False,"reason":"OPENROUTER_API_KEY missing","added":0}
  req=urllib.request.Request("https://openrouter.ai/api/v1/models",headers={"Authorization":"Bearer "+key})
  with urllib.request.urlopen(req,timeout=15) as r: data=json.loads(r.read().decode())
  added=0
  existing={(m.provider,m.model) for m in self.registry.models}
  for x in data.get("data",[])[:limit]:
   slug=x.get("id","")
   if not slug: continue
   pricing=x.get("pricing") or {}
   is_free=(pricing.get("prompt") in (0,"0","0.0") and pricing.get("completion") in (0,"0","0.0")) or slug.endswith(":free")
   params=set(x.get("supported_parameters") or [])
   tools="tools" in params
   roles={"researcher","planner","reviewer"} if tools else {"researcher"}
   if any(k in slug.lower() for k in ("code","coder","qwen","devstral","codestral")): roles.add("executor")
   if is_free: priority=60
   else: priority=90
   if ("openrouter",slug) not in existing:
    self.registry.models.append(ModelCandidate("openrouter",slug,roles,free=is_free,tool_capable=tools,priority=priority)); added+=1
  return {"ok":True,"added":added,"total":len(self.registry.models)}
 def refresh_free_pool(self):
  if os.getenv("OPENROUTER_API_KEY"):
   for m in self.registry.models:
    if m.provider=="openrouter" and m.model=="openrouter/free": m.free=True
  return self.pool()
 def _available(self,m):
  keys={"anthropic":"ANTHROPIC_API_KEY","openai":"OPENAI_API_KEY","google":"GEMINI_API_KEY","openrouter":"OPENROUTER_API_KEY"}
  return m.provider=="ollama" or bool(os.getenv(keys.get(m.provider,""))) or (m.provider=="anthropic" and self._claude_cli_available())
 def _claude_cli_available(self):
  import shutil
  return shutil.which("claude") is not None
 def rank(self,role,requires_tools=False,prefer_free=False):
  cs=self.registry.for_role(role)
  if requires_tools: cs=[m for m in cs if m.tool_capable]
  if prefer_free:
   free=[m for m in cs if m.free]
   if free: cs=free
  now=time.time()
  return sorted([m for m in cs if self._available(m)],key=lambda m:(self.failures.get(m.model,(0,0))[1]>now,self.score(m,role),self.failures.get(m.model,(0,0))[0]))
 def choose(self,role,*,requires_tools=False,prefer_free=False):
  cs=self.rank(role,requires_tools,prefer_free)
  if not cs: raise RuntimeError(f"No model available for role={role!r}")
  return cs[0]
 def score(self,m,role):
  s=self.stats.get(m.model,{"ok":0,"fail":0,"latency":0.0})
  role_b=self.benchmarks.get(m.provider+"/"+m.model,{}).get("roles",{}).get(role,{}).get("score")
  if role_b is not None: return (100-role_b)*0.8 + m.priority - (25 if m.free else 0) - (20 if m.tool_capable else 0)
  success=s["ok"]/(s["ok"]+s["fail"]) if s["ok"]+s["fail"] else 0.5
  latency=min(s["latency"],120.0) if s["latency"] else 10.0
  role_bonus=0 if role in m.roles else 100
  free_bonus=-25 if m.free else 0
  tool_bonus=-20 if m.tool_capable else 0
  return role_bonus + m.priority + free_bonus + tool_bonus + (1-success)*30 + latency*.25
 def report_failure(self,m,backoff=30):
  n,_=self.failures.get(m.model,(0,0));self.failures[m.model]=(n+1,time.time()+min(900,backoff*(2**n))); s=self.stats.setdefault(m.model,{"ok":0,"fail":0,"latency":0.0}); s["fail"]+=1; self._persist(m)
 def report_latency(self,m,seconds,ok=True):
  s=self.stats.setdefault(m.model,{"ok":0,"fail":0,"latency":0.0}); s["latency"]=seconds if not s["latency"] else s["latency"]*.8+seconds*.2; s["ok" if ok else "fail"]+=1; self._persist(m)
 def report_success(self,m): self.failures.pop(m.model,None); self._persist(m)
 def stats_view(self):
  return {k:{**v,"success_rate":round(v["ok"]/(v["ok"]+v["fail"]),3) if v["ok"]+v["fail"] else 0} for k,v in self.stats.items()}

 def pool(self):
  return [{"provider":m.provider,"model":m.model,"roles":sorted(m.roles),"free":m.free,"tool_capable":m.tool_capable,"priority":m.priority,"available":self._available(m),"stats":self.stats_view().get(m.model,{})} for m in self.registry.models]
 def update_model(self,provider,model,changes):
  for m in self.registry.models:
   if m.provider==provider and m.model==model:
    for k in ("priority","free","roles"):
     if k in changes: setattr(m,k,set(changes[k]) if k=="roles" else changes[k])
    return {"ok":True,"provider":provider,"model":model}
  raise KeyError("model not found")
 def test_model(self,provider,model):
  for m in self.registry.models:
   if m.provider==provider and m.model==model: return {"provider":provider,"model":model,"available":self._available(m)}
  raise KeyError("model not found")

 def benchmark_model(self,provider,model,adapter,timeout=45):
  import time,json
  tests=[
   ("planning","Create a 3-step implementation plan for a small web app. Return exactly 3 numbered steps."),
   ("coding","Write a Python function add(a,b) that returns a+b. Return code only."),
   ("reasoning","What is 17*19? Return only the integer."),
   ("json","Return exactly JSON with keys ok and value, where ok=true and value=42."),
   ("tool_use","Explain in one sentence whether you support function/tool calling.")
  ]
  results=[]; total=0.0
  for name,prompt in tests:
   started=time.time()
   try:
    r=adapter.complete(prompt,timeout=timeout)
    elapsed=time.time()-started; total+=elapsed; text=r.text.strip()
    passed=(len(text)>0 and (name!="reasoning" or "323" in text) and (name!="json" or '"ok"' in text) and (name!="coding" or "return" in text))
    results.append({"test":name,"passed":passed,"latency":round(elapsed,3)})
   except Exception as e:
    results.append({"test":name,"passed":False,"error":str(e)[:180]})
  passed=sum(1 for x in results if x["passed"])
  score=round(passed/len(results)*100,1)
  key=provider+"/"+model
  self.benchmarks[key]={"score":score,"tests":results,"total_latency":round(total,3),"updated_at":time.time()}
  return {"provider":provider,"model":model,"score":score,"tests":results}

 def role_benchmark(self,provider,model,adapter,role,timeout=45):
  import time
  suites={
   "planner":[("planning","Design a concise implementation plan for a Telegram bot feature. Return 5 ordered steps.")],
   "executor":[("coding","Write a robust Python function that validates an email and returns True or False. Code only.")],
   "researcher":[("research","List 5 factual checks you would perform before answering a question about a company. Concise bullets.")],
   "reviewer":[("review","Review this code: def add(a,b): return a+b. Give 2 useful review comments.")],
   "judge":[("reasoning","Compare options A and B using cost=3,2 and quality=7,6. Which has better quality/cost? Show calculation.")],
   "tool_agent":[("tool_use","Describe the JSON arguments you would pass to a tool named search with query='test'. Return JSON only.")]
  }
  tests=suites.get(role,suites["planner"]); results=[]
  for name,prompt in tests:
   t=time.time()
   try:
    r=adapter.complete(prompt,timeout=timeout); elapsed=time.time()-t; txt=r.text.strip()
    passed=bool(txt) and (role!="tool_agent" or "query" in txt)
    results.append({"test":name,"passed":passed,"latency":round(elapsed,3)})
   except Exception as e: results.append({"test":name,"passed":False,"error":str(e)[:180]})
  score=round(sum(x["passed"] for x in results)/len(results)*100,1)
  key=provider+"/"+model; self.benchmarks.setdefault(key,{})["roles"]={**self.benchmarks.get(key,{}).get("roles",{}),role:{"score":score,"tests":results,"updated_at":time.time()}}
  return {"provider":provider,"model":model,"role":role,"score":score,"tests":results}

 def record_task(self,m,role,success,latency,tool_calls=0,repairs=0,cost=0.0):
  with sqlite3.connect(self.db) as c: c.execute("CREATE TABLE IF NOT EXISTS task_outcomes(id INTEGER PRIMARY KEY AUTOINCREMENT,model TEXT,role TEXT,success INTEGER,latency REAL,tool_calls INTEGER,repairs INTEGER,cost REAL,created_at REAL)")
  with sqlite3.connect(self.db) as c: c.execute("INSERT INTO task_outcomes(model,role,success,latency,tool_calls,repairs,cost,created_at) VALUES(?,?,?,?,?,?,?,?)",(m.model,role,int(success),float(latency),int(tool_calls),int(repairs),float(cost),time.time()))
  self.report_latency(m,latency,success)
 def learning_view(self,role=None):
  with sqlite3.connect(self.db) as c:
   c.execute("CREATE TABLE IF NOT EXISTS task_outcomes(id INTEGER PRIMARY KEY AUTOINCREMENT,model TEXT,role TEXT,success INTEGER,latency REAL,tool_calls INTEGER,repairs INTEGER,cost REAL,created_at REAL)")
   q="SELECT model,role,COUNT(*),AVG(success),AVG(latency),AVG(tool_calls),AVG(repairs),AVG(cost) FROM task_outcomes"; args=()
   if role: q+=" WHERE role=?"; args=(role,)
   q+=" GROUP BY model,role"; rows=c.execute(q,args).fetchall()
  return [{"model":r[0],"role":r[1],"tasks":r[2],"success_rate":round(r[3],3),"latency":round(r[4],3),"tool_calls":round(r[5],2),"repairs":round(r[6],2),"cost":round(r[7],6)} for r in rows]
