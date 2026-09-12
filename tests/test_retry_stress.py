import time
from core.jobs import JobManager

def test_job_records_failed_attempt():
    mgr=JobManager(db_path="data/test_retry_stress.db")
    j=mgr.submit("retry-test",lambda job: (_ for _ in ()).throw(RuntimeError("synthetic provider failure")))
    deadline=time.time()+3
    while time.time()<deadline and j.status not in {"completed","failed"}: time.sleep(.02)
    assert j.status=="failed"
    assert len(j.attempts)>=1
    assert j.attempts[0]["status"]=="failed"
    assert "synthetic provider failure" in j.attempts[0]["error"]
