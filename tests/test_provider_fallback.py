import json

from core.adapters import OpenAICompatibleAdapter, OllamaAdapter
from core.registry import ModelRegistry
from core.router import ModelRouter


def test_openai_registry_alias_resolves_to_configured_model(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test")
    adapter = OpenAICompatibleAdapter("openai", "http://example.test/v1", "OPENAI_API_KEY", "gpt-5")
    captured = {}

    class FakeResponse:
        def read(self): return json.dumps({"choices": [{"message": {"content": "OK"}}]}).encode()
        def __enter__(self): return self
        def __exit__(self, *args): pass

    def fake_urlopen(req, timeout=0):
        captured["payload"] = json.loads(req.data.decode())
        return FakeResponse()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    assert adapter.complete("test", model="gpt").text == "OK"
    assert captured["payload"]["model"] == "gpt-5"


def test_ollama_alias_resolves_first_local_model(monkeypatch):
    monkeypatch.delenv("OLLAMA_MODEL", raising=False)
    adapter = OllamaAdapter("http://ollama.test")

    class FakeResponse:
        def __init__(self, payload): self.payload = payload
        def read(self): return json.dumps(self.payload).encode()
        def __enter__(self): return self
        def __exit__(self, *args): pass

    calls = []
    def fake_urlopen(req, timeout=0):
        calls.append(req.full_url)
        if req.full_url.endswith("/api/tags"):
            return FakeResponse({"models": [{"name": "qwen3:8b"}]})
        return FakeResponse({"message": {"content": "OK"}})

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    assert adapter.complete("test", model="local").text == "OK"
    assert calls == ["http://ollama.test/api/tags", "http://ollama.test/api/chat"]


def test_ollama_alias_uses_no_proxy_opener(monkeypatch):
    adapter = OllamaAdapter("http://ollama.test", "qwen3:8b")
    class FakeResponse:
        def read(self): return json.dumps({"message":{"content":"OK"}}).encode()
        def __enter__(self): return self
        def __exit__(self,*args): pass
    calls=[]
    def fake_open(req,timeout=0):
        calls.append(req.full_url)
        return FakeResponse()
    monkeypatch.setattr(adapter.opener,"open",fake_open)
    assert adapter.complete("test",model="local").text=="OK"
    assert calls==["http://ollama.test/api/chat"]


def test_ollama_is_tool_capable_fallback_candidate():
    registry = ModelRegistry.default()
    m = next(x for x in registry.models if x.provider == "ollama")
    assert m.tool_capable
    assert {"planner", "executor", "reviewer", "fixer"} <= m.roles


def test_router_can_select_ollama_when_claude_unavailable(monkeypatch):
    monkeypatch.setenv("OLLAMA_MODEL", "qwen3:8b")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    router = ModelRouter()
    monkeypatch.setattr(router, "_claude_cli_available", lambda: False)

    class R:
        def read(self): return json.dumps({"models": [{"name": "qwen3:8b"}]}).encode()
        def __enter__(self): return self
        def __exit__(self, *args): pass

    monkeypatch.setattr("urllib.request.urlopen", lambda req, timeout=0: R())
    m = router.choose("executor", requires_tools=True)
    assert m.provider == "ollama"
