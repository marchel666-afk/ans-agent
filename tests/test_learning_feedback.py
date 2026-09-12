import sqlite3,tempfile
from core.orchestrator import Orchestrator
from core.router import ModelRouter
from core.types import ModelCandidate
class A:
 def complete(self,*a,**k):
  class R: text="OK"
  return R()
def test_call_records_learning_success():
 with tempfile.TemporaryDirectory() as d:
  rt=ModelRouter()
  rt.db=d+"/r.db"
  m=ModelCandidate("test","m",{"planner"},priority=1)
  rt.registry.models=[m]
  o=Orchestrator(router=rt,workspace=d)
  o.adapters={"m":A()}
  assert o.call("planner","x")=="OK"
  rows=rt.learning_view("planner")
  assert rows and rows[0]["success_rate"]==1.0 and rows[0]["tasks"]==1
