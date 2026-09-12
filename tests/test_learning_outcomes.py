import sqlite3,tempfile
from core.router import ModelRouter
from core.registry import ModelRegistry
from core.types import ModelCandidate

def test_learning_outcome_changes_model_score():
    with tempfile.TemporaryDirectory() as d:
        r=ModelRegistry([ModelCandidate("x","a",{"executor"},priority=50),ModelCandidate("x","b",{"executor"},priority=50)])
        rt=ModelRouter(r); rt.db=d+"/r.db"
        rt.record_task(r.models[0],"executor",True,1)
        rt.record_task(r.models[1],"executor",False,10)
        a=rt.learning_view("executor")
        assert any(x["model"]=="a" and x["success_rate"]==1.0 for x in a)
        assert any(x["model"]=="b" and x["success_rate"]==0.0 for x in a)
