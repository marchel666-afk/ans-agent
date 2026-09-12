import tempfile
from core.router import ModelRouter
from core.registry import ModelRegistry
from core.types import ModelCandidate

def test_policy_cheap_prefers_low_cost():
 with tempfile.TemporaryDirectory() as d:
  cheap=ModelCandidate("test","cheap",{"executor"},priority=50,input_cost_per_million=1,output_cost_per_million=1)
  expensive=ModelCandidate("test","expensive",{"executor"},priority=50,input_cost_per_million=10,output_cost_per_million=10)
  rt=ModelRouter(ModelRegistry([cheap,expensive])); rt.db=d+"/r.db"
  assert rt.choose_policy("executor","cheap").model=="cheap"

def test_policy_quality_prefers_success():
 with tempfile.TemporaryDirectory() as d:
  good=ModelCandidate("test","good",{"executor"},priority=50,input_cost_per_million=10,output_cost_per_million=10)
  bad=ModelCandidate("test","bad",{"executor"},priority=50,input_cost_per_million=1,output_cost_per_million=1)
  rt=ModelRouter(ModelRegistry([good,bad])); rt.db=d+"/r.db"
  for _ in range(8):
   rt.record_task(good,"executor",True,1)
   rt.record_task(bad,"executor",False,1)
  assert rt.choose_policy("executor","quality").model=="good"

def test_budget_filters_when_possible():
 with tempfile.TemporaryDirectory() as d:
  cheap=ModelCandidate("test","cheap",{"planner"},priority=50,input_cost_per_million=1,output_cost_per_million=1)
  expensive=ModelCandidate("test","expensive",{"planner"},priority=1,input_cost_per_million=100,output_cost_per_million=100)
  rt=ModelRouter(ModelRegistry([cheap,expensive])); rt.db=d+"/r.db"
  assert rt.choose_policy("planner","balanced",budget=.01).model=="cheap"
