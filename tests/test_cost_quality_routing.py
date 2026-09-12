import tempfile
from core.router import ModelRouter
from core.registry import ModelRegistry
from core.types import ModelCandidate

def test_ranking_prefers_quality_when_cost_is_similar():
    with tempfile.TemporaryDirectory() as d:
        good=ModelCandidate("test","good",{"executor"},priority=50,input_cost_per_million=1,output_cost_per_million=1)
        bad=ModelCandidate("test","bad",{"executor"},priority=50,input_cost_per_million=1,output_cost_per_million=1)
        rt=ModelRouter(ModelRegistry([good,bad])); rt.db=d+"/r.db"
        for _ in range(10):
            rt.record_task(good,"executor",True,1)
            rt.record_task(bad,"executor",False,1)
        assert rt.rank("executor")[0].model=="good"

def test_budget_rank_exposes_estimated_cost():
    with tempfile.TemporaryDirectory() as d:
        m=ModelCandidate("test","m",{"planner"},priority=50,input_cost_per_million=2,output_cost_per_million=4)
        rt=ModelRouter(ModelRegistry([m])); rt.db=d+"/r.db"
        result=rt.estimate_task_budget("planner",4000,2000,0.1)
        assert result[0]["estimated_cost"] == 0.016
