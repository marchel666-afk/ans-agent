import time
from core.jobs import JobManager
def test_job_persistence(tmp_path):
 p=str(tmp_path/"jobs.db"); jm=JobManager(p); j=jm.submit("s",lambda _:{"ok":1})
 for _ in range(50):
  if jm.get(j.id).status=="completed": break
  time.sleep(.02)
 jm2=JobManager(p); r=jm2.get(j.id)
 assert r and r.status=="completed" and r.result["ok"]==1
def test_cancel(tmp_path):
 jm=JobManager(str(tmp_path/"jobs.db")); j=jm.submit("s",lambda job: {"ok":1})
 assert jm.cancel(j.id)
 assert jm.get(j.id).status=="cancelled"


def test_job_lifecycle_records_attempt(tmp_path):
 import time
 jm=JobManager(str(tmp_path/"jobs.db"))
 j=jm.submit("s",lambda job: {"status":"ok","job_id":job.id})
 for _ in range(100):
  if jm.get(j.id).status=="completed": break
  time.sleep(.01)
 r=jm.get(j.id)
 assert r.status=="completed"
 assert r.result["status"]=="ok"
 assert len(r.attempts)==1
 assert r.attempts[0]["status"]=="completed"
