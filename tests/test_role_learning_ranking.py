import tempfile
from core.router import ModelRouter
from core.registry import ModelRegistry
from core.types import ModelCandidate

def test_role_specific_learning_affects_ranking():
    with tempfile.TemporaryDirectory() as d:
        a=ModelCandidate("test","planner-good",{"planner"},priority=50)
        b=ModelCandidate("test","planner-bad",{"planner"},priority=50)
        reg=ModelRegistry([a,b])
        rt=ModelRouter(reg); rt.db=d+"/router.db"
        for _ in range(6):
            rt.record_task(a,"planner",True,1.0)
            rt.record_task(b,"planner",False,1.0)
        ranked=rt.rank("planner")
        assert ranked[0].model=="planner-good"

def test_learning_is_role_specific():
    with tempfile.TemporaryDirectory() as d:
        a=ModelCandidate("test","dual",{"planner","executor"},priority=50)
        b=ModelCandidate("test","dual2",{"planner","executor"},priority=50)
        reg=ModelRegistry([a,b])
        rt=ModelRouter(reg); rt.db=d+"/router.db"
        for _ in range(5):
            rt.record_task(a,"planner",True,1.0)
            rt.record_task(b,"planner",False,1.0)
            rt.record_task(a,"executor",False,1.0)
            rt.record_task(b,"executor",True,1.0)
        assert rt.rank("planner")[0].model=="dual"
        assert rt.rank("executor")[0].model=="dual2"
