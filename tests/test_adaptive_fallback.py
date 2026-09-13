import tempfile
from core.router import ModelRouter
from core.registry import ModelRegistry
from core.types import ModelCandidate

def test_weekly_limit_fallback_avoids_anthropic():
 with tempfile.TemporaryDirectory() as d:
  a=ModelCandidate("anthropic","a",{"planner"},priority=1)
  o=ModelCandidate("ollama","o",{"planner"},priority=2)
  rt=ModelRouter(ModelRegistry([a,o])); rt.db=d+"/r.db"
  rt._available=lambda m: True
  xs=rt.fallback_policy("weekly_limit","planner","balanced")
  assert all(x.provider!="anthropic" for x in xs)

def test_timeout_fallback_prefers_non_anthropic():
 with tempfile.TemporaryDirectory() as d:
  a=ModelCandidate("anthropic","a",{"planner"},priority=1)
  o=ModelCandidate("ollama","o",{"planner"},priority=2)
  rt=ModelRouter(ModelRegistry([a,o])); rt.db=d+"/r.db"
  rt._available=lambda m: True
  assert rt.fallback_policy("timeout","planner")[0].provider!="anthropic"


def test_circuit_opens_after_failure_and_recovers():
 with tempfile.TemporaryDirectory() as d:
  m=ModelCandidate("test","m",{"planner"},priority=1)
  rt=ModelRouter(ModelRegistry([m])); rt.db=d+"/r.db"
  rt.report_failure(m,backoff=60,error="weekly limit")
  assert rt.circuit_view()["m"]["state"]=="open"
  rt.failures["m"]=(rt.failures["m"][0],0,"weekly_limit")
  rt.rank("planner")
  assert rt.circuit_view()["m"]["state"]=="half-open"
  rt.report_success(m)
  assert rt.circuit_view()["m"]["state"]=="closed"


def test_failure_path_selects_fallback_after_opening_circuit():
 with tempfile.TemporaryDirectory() as d:
  a=ModelCandidate("anthropic","a",{"planner"},priority=1)
  o=ModelCandidate("ollama","o",{"planner"},priority=2)
  rt=ModelRouter(ModelRegistry([a,o])); rt.db=d+"/r.db"
  rt._available=lambda m: True
  rt.report_failure(a,error="weekly limit")
  assert rt.circuit_view()["a"]["state"]=="open"
  xs=rt.fallback_policy("weekly_limit","planner",exclude={"a"})
  assert xs and xs[0].model=="o"
  rt.report_success(o)
  assert rt.circuit_view()["a"]["state"]=="open"


def test_orchestrator_call_retries_on_fallback(monkeypatch):
 from core.orchestrator import Orchestrator
 class A:
  def __init__(self,name): self.name=name
  def complete(self,*args,**kwargs):
   if self.name=="a": raise RuntimeError("weekly limit")
   return type("R",(),{"text":"OK"})()
 a=ModelCandidate("anthropic","a",{"planner"},priority=1)
 o=ModelCandidate("ollama","o",{"planner"},priority=2)
 rt=ModelRouter(ModelRegistry([a,o]))
 rt._available=lambda m: True
 orch=Orchestrator(router=rt)
 orch.adapters={"a":A("a"),"o":A("o")}
 assert orch.call("planner","smoke")=="OK"
 assert rt.circuit_view()["a"]["state"]=="open"


def test_executor_failure_uses_fallback_and_records_attempts():
 from core.orchestrator import Orchestrator
 class A:
  def __init__(self,name): self.name=name
  def complete(self,*args,**kwargs):
   if self.name=="a": raise RuntimeError("weekly limit")
   return type("R",(),{"text":"PASS"})()
 a=ModelCandidate("anthropic","a",{"planner","executor","reviewer","fixer"},priority=1)
 o=ModelCandidate("ollama","o",{"planner","executor","reviewer","fixer"},priority=2)
 rt=ModelRouter(ModelRegistry([a,o]))
 rt._available=lambda m: True
 orch=Orchestrator(router=rt)
 orch.adapters={"a":A("a"),"o":A("o")}
 orch.workspace="."
 orch.job=type("J",(),{"attempts":[]})()
 orch.job_manager=None
 monkeypatch = __import__("pytest").MonkeyPatch()
 monkeypatch.setattr("core.orchestrator.ToolLoop",lambda adapter,*args,**kwargs:type("L",(),{"run":lambda self,*a,**k: adapter.complete("").text})())
 try:
  result=orch.run("smoke","agent",1)
  assert result["status"] in {"completed","max_iterations"}
  assert rt.circuit_view()["a"]["state"]=="open"
 finally:
  monkeypatch.undo()
