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
  self.registry=registry or ModelRegistry.default(); self.failures={}; self.half_open=set()
  self.db=os.getenv("ANS_ROUTER_DB","./data/router_stats.db"); os.makedirs(os.path.dirname(self.db) or ".",exist_ok=True)
  self.stats={}; self.benchmarks={}; self.health_db_ready=False
  with sqlite3.connect(self.db) as c:
   c.execute("CREATE TABLE IF NOT EXISTS model_stats(model TEXT PRIMARY KEY, ok INTEGER DEFAULT 0, fail INTEGER DEFAULT 0, latency REAL DEFAULT 0)")
   c.execute("CREATE TABLE IF NOT EXISTS provider_health(model TEXT PRIMARY KEY, failures INTEGER DEFAULT 0, cooldown_until REAL DEFAULT 0, category TEXT DEFAULT '', updated_at REAL DEFAULT 0)")
   for model,ok,fail,lat in c.execute("SELECT model,ok,fail,latency FROM model_stats"): self.stats[model]={"ok":ok,"fail":fail,"latency":lat}
   for model,n,until,category,updated in c.execute("SELECT model,failures,cooldown_until,category,updated_at FROM provider_health"):
    if until > time.time(): self.failures[model]=(n,until,category)
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
  if m.provider=="ollama":
   try:
    import urllib.request, json
    base=os.getenv("OLLAMA_BASE_URL","http://127.0.0.1:11434").rstrip("/")
    with urllib.request.urlopen(base+"/api/tags",timeout=1.5) as r: data=json.loads(r.read().decode())
    wanted=os.getenv("OLLAMA_MODEL","").strip()
    models=[x.get("name","") for x in data.get("models",[])]
    return bool(models) and (not wanted or any(x==wanted or x.startswith(wanted+":") for x in models))
   except Exception:
    return False
  return bool(os.getenv(keys.get(m.provider,""))) or (m.provider=="anthropic" and self._claude_cli_available())
 def _claude_cli_available(self):
  import shutil
  return shutil.which("claude") is not None
 def rank(self,role,requires_tools=False,prefer_free=False,max_cost=None):
  cs=self.registry.for_role(role)
  if requires_tools: cs=[m for m in cs if m.tool_capable]
  if prefer_free:
   free=[m for m in cs if m.free]
   if free: cs=free
  now=time.time()
  active=[]; expired=[]
  for m in cs:
   state=self.failures.get(m.model)
   if state and state[1] <= now:
    self.failures.pop(m.model,None); self.half_open.add(m.model)
   if self._available(m) and (max_cost is None or m.input_cost_per_million+m.output_cost_per_million<=max_cost):
    active.append(m)
  if expired:
   with sqlite3.connect(self.db) as c:
    for model in expired: c.execute("DELETE FROM provider_health WHERE model=?",(model,))
  active=[m for m in active if m.model not in self.failures or m.model in self.half_open]
  return sorted(active,key=lambda m:(0 if m.model in self.half_open else 1,self.score(m,role),self.failures.get(m.model,(0,0,""))[0]))
 def choose(self,role,*,requires_tools=False,prefer_free=False,max_cost=None):
  cs=self.rank(role,requires_tools,prefer_free,max_cost)
  if not cs: raise RuntimeError(f"No model available for role={role!r}")
  return cs[0]
 def score(self,m,role):
  s=self.stats.get(m.model,{"ok":0,"fail":0,"latency":0.0})
  role_b=self.benchmarks.get(m.provider+"/"+m.model,{}).get("roles",{}).get(role,{}).get("score")
  success=s["ok"]/(s["ok"]+s["fail"]) if s["ok"]+s["fail"] else 0.5
  latency=min(s["latency"],120.0) if s["latency"] else 10.0
  role_bonus=0 if role in m.roles else 100
  free_bonus=-25 if m.free else 0
  tool_bonus=-20 if m.tool_capable else 0
  rs=self._role_outcome(m.model,role)
  if rs["tasks"]>0:
   n=rs["tasks"]
   role_success=(rs["successes"]+2.0)/(n+4.0)
   role_latency=rs["latency"] or latency
  else:
   role_success=success
   role_latency=latency
  # Lower is better. Quality is rewarded, while latency and estimated cost
  # are penalized. Static priority remains a tie-breaker rather than the sole signal.
  quality_penalty=(1-role_success)*55
  latency_penalty=min(role_latency,120.0)*0.18
  estimated_cost=self.cost_estimate(m,4000,2000)
  cost_penalty=min(estimated_cost*1000.0,40.0)
  benchmark_penalty=(100-role_b)*0.25 if role_b is not None else 0
  return role_bonus + m.priority + free_bonus + tool_bonus + quality_penalty + latency_penalty + cost_penalty + benchmark_penalty

 def _role_outcome(self,model,role):
  with sqlite3.connect(self.db) as c:
   c.execute("CREATE TABLE IF NOT EXISTS task_outcomes(id INTEGER PRIMARY KEY AUTOINCREMENT,model TEXT,role TEXT,success INTEGER,latency REAL,tool_calls INTEGER,repairs INTEGER,cost REAL,created_at REAL)")
   row=c.execute("SELECT COUNT(*),COALESCE(SUM(success),0),COALESCE(AVG(latency),0) FROM task_outcomes WHERE model=? AND role=?",(model,role)).fetchone()
  return {"tasks":row[0],"successes":row[1],"latency":row[2]}
 def classify_failure(self,error):
  text=str(error).lower()
  if "weekly limit" in text or "weekly usage" in text or "resets " in text:
   return "weekly_limit",int(os.getenv("ANS_WEEKLY_LIMIT_COOLDOWN", "21600"))
  if "rate limit" in text or "429" in text or "too many requests" in text:
   return "rate_limit",300
  if "unauthorized" in text or "invalid api key" in text or "missing " in text and "key" in text:
   return "auth",1800
  if "timeout" in text or "timed out" in text:
   return "timeout",120
  return "provider_error",30

 def fallback_policy(self,category,role,policy="balanced"):
  base=self.policy_rank(role,policy)
  if category in {"auth","weekly_limit"}:
   return [m for m in base if m.provider != "anthropic"] or base
  if category in {"rate_limit","timeout"}:
   return sorted(base,key=lambda m:(m.provider=="anthropic",self.score(m,role)))
  return base

 def report_failure(self,m,backoff=30,error=None):
  self.half_open.discard(m.model)
  n,*_=self.failures.get(m.model,(0,0))
  category,base=self.classify_failure(error or "")
  if error is not None: backoff=base
  cooldown=min(900,backoff*(2**n))
  if category=="weekly_limit": cooldown=max(base,cooldown)
  until=time.time()+cooldown
  self.failures[m.model]=(n+1,until,category)
  with sqlite3.connect(self.db) as c: c.execute("INSERT INTO provider_health(model,failures,cooldown_until,category,updated_at) VALUES(?,?,?,?,?) ON CONFLICT(model) DO UPDATE SET failures=excluded.failures,cooldown_until=excluded.cooldown_until,category=excluded.category,updated_at=excluded.updated_at",(m.model,n+1,until,category,time.time()))
  s=self.stats.setdefault(m.model,{"ok":0,"fail":0,"latency":0.0}); s["fail"]+=1; self._persist(m)
  return {"category":category,"cooldown_seconds":cooldown}
 def report_latency(self,m,seconds,ok=True):
  s=self.stats.setdefault(m.model,{"ok":0,"fail":0,"latency":0.0}); s["latency"]=seconds if not s["latency"] else s["latency"]*.8+seconds*.2; s["ok" if ok else "fail"]+=1; self._persist(m)
 def report_success(self,m):
  recovered=m.model in self.half_open
  self.half_open.discard(m.model)
  self.failures.pop(m.model,None); self._persist(m)
  with sqlite3.connect(self.db) as c: c.execute("DELETE FROM provider_health WHERE model=?",(m.model,))
  return {"ok":True}
 def circuit_view(self):
  now=time.time(); out={}
  for m in self.registry.models:
   state=self.failures.get(m.model)
   if state:
    n,until,category=state
    out[m.model]={"state":"open","failures":n,"category":category,"cooldown_remaining":max(0,round(until-now,1))}
   elif m.model in self.half_open:
    out[m.model]={"state":"half-open","failures":0,"category":"","cooldown_remaining":0}
   else:
    out[m.model]={"state":"closed","failures":0,"category":"","cooldown_remaining":0}
  return out

 def stats_view(self):
  return {k:{**v,"success_rate":round(v["ok"]/(v["ok"]+v["fail"]),3) if v["ok"]+v["fail"] else 0} for k,v in self.stats.items()}

 def pool(self):
  return [{"provider":m.provider,"model":m.model,"roles":sorted(m.roles),"free":m.free,"tool_capable":m.tool_capable,"priority":m.priority,"available":self._available(m),"stats":self.stats_view().get(m.model,{})} for m in self.registry.models]
 def cost_estimate(self,m,input_tokens,output_tokens):
  return (input_tokens/1_000_000)*m.input_cost_per_million+(output_tokens/1_000_000)*m.output_cost_per_million
 def budget_rank(self,role,budget,requires_tools=False):
  cs=self.rank(role,requires_tools)
  return sorted(cs,key=lambda m:(self.score(m,role),self.cost_estimate(m,4000,2000)/max(budget,0.000001)))

 def policy_rank(self,role,policy="balanced",requires_tools=False,budget=None):
  policy=(policy or "balanced").lower()
  if policy not in {"cheap","balanced","quality"}: policy="balanced"
  cs=self.rank(role,requires_tools)
  if not cs: return []
  if budget is not None:
   cs=[m for m in cs if self.cost_estimate(m,4000,2000)<=budget] or cs
  def key(m):
   rs=self._role_outcome(m.model,role); n=rs["tasks"]
   success=(rs["successes"]+2)/(n+4) if n else .5
   latency=rs["latency"] or 10
   cost=self.cost_estimate(m,4000,2000)
   if policy=="cheap": return (cost, (1-success), latency, self.score(m,role))
   if policy=="quality": return ((1-success), -m.priority, latency, cost)
   return (self.score(m,role), cost, latency)
  return sorted(cs,key=key)

 def choose_policy(self,role,policy="balanced",requires_tools=False,budget=None):
  cs=self.policy_rank(role,policy,requires_tools,budget)
  if not cs: raise RuntimeError(f"No model available for role={role!r} policy={policy!r}")
  return cs[0]

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

 def learning_view(self,role=None):
  with sqlite3.connect(self.db) as c:
   c.execute("CREATE TABLE IF NOT EXISTS task_outcomes(id INTEGER PRIMARY KEY AUTOINCREMENT,model TEXT,role TEXT,success INTEGER,latency REAL,tool_calls INTEGER,repairs INTEGER,cost REAL,created_at REAL)")
   q="SELECT model,role,COUNT(*),AVG(success),AVG(latency),AVG(tool_calls),AVG(repairs),AVG(cost) FROM task_outcomes"; args=()
   if role: q+=" WHERE role=?"; args=(role,)
   q+=" GROUP BY model,role"
   rows=c.execute(q,args).fetchall()
  return [{"model":r[0],"role":r[1],"tasks":r[2],"success_rate":round(r[3],3),"latency":round(r[4],3),"tool_calls":round(r[5],2),"repairs":round(r[6],2),"cost":round(r[7],6)} for r in rows]

 def estimate_task_budget(self,role,input_tokens=4000,output_tokens=2000,budget=None,requires_tools=False):
  ranked=self.budget_rank(role,budget or 0.01,requires_tools)
  return [{"provider":m.provider,"model":m.model,"estimated_cost":self.cost_estimate(m,input_tokens,output_tokens),"score":self.score(m,role)} for m in ranked]
