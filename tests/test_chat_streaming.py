"""Streaming adapters and the /chat SSE endpoint (hermetic)."""
import json

import app
from core.adapters import OllamaAdapter, OpenAICompatibleAdapter, ClaudeCodeAdapter
from fastapi.testclient import TestClient

client = TestClient(app.app)


class _Lines:
    def __init__(self, lines):
        self._lines = lines

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def __iter__(self):
        return iter(self._lines)


def test_ollama_stream_yields_deltas(monkeypatch):
    adapter = OllamaAdapter("http://ollama.test", "llama3.2")
    lines = [
        b'{"message":{"content":"He"}}\n',
        b'{"message":{"content":"llo"}}\n',
        b'{"message":{"content":"!"},"done":true}\n',
    ]
    monkeypatch.setattr(adapter.opener, "open", lambda req, timeout=0: _Lines(lines))
    assert "".join(adapter.stream("hi")) == "Hello!"


def test_openai_stream_yields_deltas(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "k")
    adapter = OpenAICompatibleAdapter("openai", "http://x/v1", "OPENAI_API_KEY", "gpt-5")
    lines = [
        b'data: {"choices":[{"delta":{"content":"Hi"}}]}\n',
        b'data: {"choices":[{"delta":{"content":" there"}}]}\n',
        b"data: [DONE]\n",
    ]
    monkeypatch.setattr("urllib.request.urlopen", lambda req, timeout=0: _Lines(lines))
    assert "".join(adapter.stream("hi")) == "Hi there"


def test_claude_stream_single_chunk(monkeypatch):
    a = ClaudeCodeAdapter()
    monkeypatch.setattr(a, "complete", lambda prompt, **k: type("R", (), {"text": "whole answer"})())
    assert list(a.stream("hi")) == ["whole answer"]


def test_chat_endpoint_streams_and_records_history(monkeypatch):
    monkeypatch.setattr(app, "AUTH_TOKEN", "test-token")
    monkeypatch.setattr(
        "core.adapters.OllamaAdapter.stream",
        lambda self, prompt, **k: iter(["Hel", "lo"]),
    )
    h = {"Authorization": "Bearer test-token"}
    r = client.post("/chat", headers=h, json={"message": "hi", "provider": "ollama", "model": "llama3.2"})
    assert r.status_code == 200
    events = [json.loads(l[5:]) for l in r.text.splitlines() if l.startswith("data:")]
    types = [e["type"] for e in events]
    assert types[0] == "start" and "delta" in types and types[-1] == "done"
    assert "".join(e["content"] for e in events if e["type"] == "delta") == "Hello"
    sid = events[0]["session_id"]
    s = client.get("/sessions/" + sid, headers=h).json()
    kinds = [e["kind"] for e in s["events"]]
    assert "chat.user" in kinds and "chat.assistant" in kinds


def test_chat_requires_auth():
    r = client.post("/chat", json={"message": "hi"})
    assert r.status_code == 401


def test_chat_rejects_empty_message(monkeypatch):
    monkeypatch.setattr(app, "AUTH_TOKEN", "test-token")
    r = client.post("/chat", headers={"Authorization": "Bearer test-token"}, json={"message": "   "})
    assert r.status_code == 400
