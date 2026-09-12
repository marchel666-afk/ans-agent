import os,time
from dataclasses import dataclass
from .registry import ModelRegistry
from .types import ModelCandidate
@dataclass
class RouteDecision:
 candidate: ModelCandidate
 reason: str
class ModelRouter:
 def __init__(self,registry=None): self.registry=registry or ModelRegistry.default(); self.failures={}
 def _available(self,m):
  keys={"anthropic":"ANTHROPIC_API_KEY","openai":"OPENAI_API_KEY","google":"GEMINI_API_KEY","openrouter":"OPENROUTER_API_KEY"}
  return m.provider=="ollama" or bool(os.getenv(keys.get(m.provider,"")))
 def rank(self,role,requires_tools=False,prefer_free=False):
  cs=self.registry.for_role(role)
  if requires_tools: cs=[m for m in cs if m.tool_capable]
  if prefer_free:
   free=[m for m in cs if m.free]
   if free: cs=free
  now=time.time()
  return sorted([m for m in cs if self._available(m) or m.provider=="anthropic"],key=lambda m:(self.failures.get(m.model,(0,0))[1]>now,m.priority,self.failures.get(m.model,(0,0))[0]))
 def choose(self,role,*,requires_tools=False,prefer_free=False):
  cs=self.rank(role,requires_tools,prefer_free)
  if not cs: raise RuntimeError(f"No model available for role={role!r}")
  return cs[0]
 def report_failure(self,m,backoff=30):
  n,_=self.failures.get(m.model,(0,0)); self.failures[m.model]=(n+1,time.time()+min(900,backoff*(2**n)))
 def report_success(self,m): self.failures.pop(m.model,None)
