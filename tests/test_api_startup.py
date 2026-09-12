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
