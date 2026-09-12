from fastapi.testclient import TestClient
import app

client=TestClient(app.app)

def test_health():
    r=client.get('/health')
    assert r.status_code==200
    assert r.json()['status']=='ok'

def test_protected_requires_auth():
    r=client.get('/diagnostics')
    assert r.status_code==401

def test_workspace_api_with_auth(monkeypatch):
    monkeypatch.setattr(app,'AUTH_TOKEN','test-token')
    r=client.get('/workspace/files',headers={'Authorization':'Bearer test-token'})
    assert r.status_code==200
    assert 'files' in r.json()


def test_production_preflight_endpoints(monkeypatch):
    monkeypatch.setattr(app,'AUTH_TOKEN','test-token')
    h={'Authorization':'Bearer test-token'}
    for path in ['/startup','/diagnostics','/model-pool','/sessions','/workspace/status','/workspace/diff','/circuit-breakers']:
        r=client.get(path,headers=h)
        assert r.status_code == 200, (path,r.status_code,r.text)
    assert 'circuits' in client.get('/circuit-breakers',headers=h).json()


def test_run_job_lifecycle_with_mock_orchestrator(monkeypatch):
    monkeypatch.setattr(app,'AUTH_TOKEN','test-token')
    class FakeOrch:
        def __init__(self,*args,**kwargs):
            self.job_manager=None; self.job=None
        def run(self,task,mode,max_iterations,policy="balanced",budget=None):
            return {"status":"completed","plan":[],"completed":["mock-step"],"observations":["mock"],"iterations":1}
    monkeypatch.setattr(app,'Orchestrator',FakeOrch)
    h={'Authorization':'Bearer test-token'}
    r=client.post('/run',headers=h,json={"task":"integration smoke","mode":"agent","max_iterations":1})
    assert r.status_code==200, r.text
    data=r.json(); assert data["job_id"] and data["session_id"]
    import time
    for _ in range(100):
        j=client.get('/jobs/'+data["job_id"],headers=h).json()
        if j["status"]=="completed": break
        time.sleep(.01)
    assert j["status"]=="completed"
    assert j["result"]["status"]=="completed"
    s=client.get('/sessions/'+data["session_id"],headers=h).json()
    kinds=[e["kind"] for e in s["events"]]
    assert "run.started" in kinds and "job.created" in kinds and "run.completed" in kinds


def test_websocket_replays_session_events(monkeypatch):
    monkeypatch.setattr(app,'AUTH_TOKEN','test-token')
    sid="ws-smoke"
    s=app.sessions.create("ws test","agent")
    s.id=sid
    s.events=[{"kind":"run.started","message":"started"},{"kind":"run.completed","message":"done"}]
    app.sessions.sessions[sid]=s
    with client.websocket_connect("/ws/"+sid+"?token=test-token") as ws:
        assert ws.receive_json()["kind"]=="run.started"
        assert ws.receive_json()["kind"]=="run.completed"
