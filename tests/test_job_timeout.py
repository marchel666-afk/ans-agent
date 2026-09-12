from core.jobs import JobManager
import time


def test_job_timeout_guard(tmp_path):
    events=[]
    jm=JobManager(str(tmp_path/"jobs.db"),emit=lambda *a,**k: events.append((a,k)))
    job=jm.submit("s",lambda j: time.sleep(0.03),timeout_seconds=0.01)
    deadline=time.time()+2
    while job.status in {"queued","running"} and time.time()<deadline: time.sleep(0.01)
    assert job.status=="failed"
    assert "timeout" in (job.error or "").lower()
