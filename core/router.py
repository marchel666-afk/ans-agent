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
  self.stats={}
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
