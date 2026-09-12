from pathlib import Path
def test_core_files_exist():
    required=["app.py","run.py","core/jobs.py","core/profiles.py","core/router.py","core/orchestrator.py","core/tool_executor.py","web/index.html","web/app.js"]
    for p in required: assert Path(p).exists(),p
def test_workspace_boundary(tmp_path):
    from core.tools import Workspace
    ws=Workspace(tmp_path); ws.write("ok.txt","x"); assert ws.read("ok.txt")=="x"
    try: ws.read("../escape.txt")
    except ValueError: pass
    else: raise AssertionError("workspace escape was allowed")
def test_job_lifecycle():
    from core.jobs import JobManager
    import time
    jm=JobManager(); done=[]
    j=jm.submit("s1",lambda job: done.append(1) or {"status":"completed"})
    for _ in range(30):
        if jm.get(j.id).status=="completed": break
        time.sleep(.05)
    assert jm.get(j.id).status=="completed"; assert done==[1]


def test_cancelled_job_does_not_complete():
    import time
    from core.jobs import JobManager
    jm=JobManager();
    def work(job):
        while not job.cancel_requested: time.sleep(.01)
        return {"should":"not complete"}
    j=jm.submit("s1",work)
    time.sleep(.03); assert jm.cancel(j.id)
    for _ in range(30):
        if jm.get(j.id).status=="cancelled": break
        time.sleep(.02)
    assert jm.get(j.id).status=="cancelled"
