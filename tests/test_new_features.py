"""Tests for the added online providers, auth-check endpoint and history access."""
import io, json
import app as appmod
from fastapi.testclient import TestClient
from core import adapters as A
from core.registry import ModelRegistry
from core.router import ModelRouter

client = TestClient(appmod.app)


# ---------- Anthropic native adapter ----------
def test_anthropic_complete_parses_messages(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    body = json.dumps({"content": [{"type": "text", "text": "привет"}]}).encode()

    class R:
        def read(self): return body
        def __enter__(self): return self
        def __exit__(self, *a): return False
    monkeypatch.setattr(A.urllib.request, "urlopen", lambda req, timeout=0: R())
    ad = A.AnthropicAdapter("claude-sonnet-4-5")
    assert ad.complete("hi").text == "привет"


def test_anthropic_stream_yields_text(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    lines = [
        b'data: {"type":"content_block_delta","delta":{"text":"aa"}}',
        b'data: {"type":"content_block_delta","delta":{"text":"bb"}}',
        b'data: [DONE]',
    ]
    monkeypatch.setattr(A.urllib.request, "urlopen", lambda req, timeout=0: io.BytesIO(b"\n".join(lines)))
    ad = A.AnthropicAdapter("claude-sonnet-4-5")
    assert "".join(ad.stream("hi")) == "aabb"


def test_anthropic_missing_key_raises(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    try:
        A.AnthropicAdapter().complete("hi")
        assert False, "expected ProviderError"
    except A.ProviderError:
        pass


# ---------- build_adapters wiring ----------
def test_build_adapters_includes_new_providers(monkeypatch):
    for k in ("ANTHROPIC_API_KEY", "GROQ_API_KEY", "OPENAI_API_KEY"):
        monkeypatch.setenv(k, "x")
    out = A.build_adapters()
    assert {"anthropic", "groq", "openai", "claude-code", "ollama"} <= set(out)


# ---------- registry / router availability ----------
def test_registry_has_api_claude_and_groq():
    models = {(m.provider, m.model) for m in ModelRegistry.default().models}
    assert ("groq", "llama-3.3-70b-versatile") in models
    assert ("anthropic", "claude-code") in models
    assert any(p == "anthropic" and m != "claude-code" for p, m in models)


def test_router_gates_by_key(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    reg = ModelRegistry.default(); rt = ModelRouter(reg)
    groq = next(m for m in reg.models if m.provider == "groq")
    api_claude = next(m for m in reg.models if m.provider == "anthropic" and m.model != "claude-code")
    assert rt._available(groq) is False
    assert rt._available(api_claude) is False
    monkeypatch.setenv("GROQ_API_KEY", "x")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    assert rt._available(groq) is True
    assert rt._available(api_claude) is True


# ---------- auth-check endpoint ----------
def test_auth_check(monkeypatch):
    monkeypatch.setattr(appmod, "AUTH_TOKEN", "tok")
    assert client.get("/auth/check").status_code == 401
    assert client.get("/auth/check", headers={"Authorization": "Bearer tok"}).status_code == 200


# ---------- history: session events are retrievable for replay ----------
def test_session_events_retrievable(monkeypatch):
    monkeypatch.setattr(appmod, "AUTH_TOKEN", "tok")
    h = {"Authorization": "Bearer tok"}
    s = appmod.sessions.create("тестовая задача", "chat")
    # app records to both the in-memory session and the DB (as /chat does)
    s.emit("chat.user", "привет"); appmod.sessions.emit(s.id, "chat.user", "привет")
    s.emit("chat.assistant", "здравствуйте"); appmod.sessions.emit(s.id, "chat.assistant", "здравствуйте")
    r = client.get(f"/sessions/{s.id}", headers=h)
    assert r.status_code == 200
    kinds = [e["kind"] for e in r.json()["events"]]
    assert "chat.user" in kinds and "chat.assistant" in kinds


def test_session_history_persists_after_restart(monkeypatch, tmp_path):
    # A fresh store (simulating a restart) must reload dialogue events from the DB
    # so the user can reopen previous conversations.
    from core.session import SessionStore
    db = str(tmp_path / "ans.db")
    st = SessionStore(db)
    s = st.create("прошлый диалог", "chat")
    st.emit(s.id, "chat.user", "вопрос")
    st.emit(s.id, "chat.assistant", "ответ")
    st2 = SessionStore(db)  # cold cache -> must read from DB
    loaded = st2.get(s.id)
    assert loaded is not None
    kinds = [e["kind"] for e in loaded.events]
    assert kinds == ["chat.user", "chat.assistant"]
