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
