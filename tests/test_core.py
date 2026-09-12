import sys
sys.path.insert(0,".")
from core.approval import ApprovalManager
from core.memory import ProjectMemory
from core.session import SessionStore
from core.task_graph import TaskGraph
from core.types import ModelCandidate

def test_memory_roundtrip(tmp_path):
    s=SessionStore(str(tmp_path/"db.sqlite"))
    m=ProjectMemory(s,"p"); m.remember("stack","FastAPI")
    assert "FastAPI" in m.get_context()

def test_approval_safe():
    a=ApprovalManager()
    assert a.requires_confirmation("read_file",{"path":"x"},autonomous=True) is False

def test_task_graph_dependencies():
    g=TaskGraph(["A","B","C"])
    assert [x.id for x in g.ready()]==["step-1"]
    g.complete("step-1","ok")
    assert {x.id for x in g.ready()}=={"step-2"}

def test_pricing():
    m=ModelCandidate(provider="x",model="y",input_cost_per_million=1,output_cost_per_million=2)
    assert m.input_cost_per_million+m.output_cost_per_million==3


def test_approval_dangerous():
    a=ApprovalManager()
    assert a.requires_confirmation("terminal",{"command":"rm -rf /"},autonomous=True) is True
