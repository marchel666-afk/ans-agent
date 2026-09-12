import tempfile,os,time
from core.jobs import JobManager

def test_attempt_history_is_persisted():
    with tempfile.TemporaryDirectory() as d:
        db=os.path.join(d,"jobs.db")
        mgr=JobManager(db_path=db)
        done=[]
        j=mgr.submit("s",lambda job: {"ok":True})
        deadline=time.time()+3
        while time.time()<deadline and j.status not in {"completed","failed"}: time.sleep(.02)
        assert j.status=="completed"
        assert len(j.attempts)==1
        assert j.attempts[0]["status"]=="completed"
        j2=JobManager(db_path=db).get(j.id)
        assert j2.attempts[0]["status"]=="completed"
