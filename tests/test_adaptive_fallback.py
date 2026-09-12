import tempfile
from core.router import ModelRouter
from core.registry import ModelRegistry
from core.types import ModelCandidate

def test_weekly_limit_fallback_avoids_anthropic():
 with tempfile.TemporaryDirectory() as d:
  a=ModelCandidate("anthropic","a",{"planner"},priority=1)
  o=ModelCandidate("ollama","o",{"planner"},priority=2)
  rt=ModelRouter(ModelRegistry([a,o])); rt.db=d+"/r.db"
  xs=rt.fallback_policy("weekly_limit","planner","balanced")
  assert all(x.provider!="anthropic" for x in xs)

def test_timeout_fallback_prefers_non_anthropic():
 with tempfile.TemporaryDirectory() as d:
  a=ModelCandidate("anthropic","a",{"planner"},priority=1)
  o=ModelCandidate("ollama","o",{"planner"},priority=2)
  rt=ModelRouter(ModelRegistry([a,o])); rt.db=d+"/r.db"
  assert rt.fallback_policy("timeout","planner")[0].provider!="anthropic"
