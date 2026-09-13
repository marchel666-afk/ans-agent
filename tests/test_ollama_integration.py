"""Focused coverage for the Ollama fallback path and environment loading.

These are hermetic unit tests: HTTP is exercised through monkeypatched
urllib entry points (no live server), while the real end-to-end check against
a running Ollama is performed separately during deployment.
"""
import json
import urllib.request

import pytest

from core.adapters import OllamaAdapter, ProviderError
from core.config import load_dotenv
from core.registry import ModelRegistry
from core.router import ModelRouter
from core.types import ModelCandidate


class _Resp:
    def __init__(self, payload):
        self._b = json.dumps(payload).encode()

    def read(self):
        return self._b

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


# --- .env loading -----------------------------------------------------------
def test_dotenv_loads_ollama_config(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text(
        "OLLAMA_BASE_URL=http://127.0.0.1:11434\nOLLAMA_MODEL=llama3.2\n"
    )
    monkeypatch.delenv("OLLAMA_BASE_URL", raising=False)
    monkeypatch.delenv("OLLAMA_MODEL", raising=False)
    load_dotenv(str(env))
    import os

    assert os.getenv("OLLAMA_BASE_URL") == "http://127.0.0.1:11434"
    assert os.getenv("OLLAMA_MODEL") == "llama3.2"


def test_dotenv_does_not_override_existing(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text("OLLAMA_MODEL=from-file\n")
    monkeypatch.setenv("OLLAMA_MODEL", "already-set")
    load_dotenv(str(env))
    import os

    assert os.getenv("OLLAMA_MODEL") == "already-set"


# --- availability / model discovery ----------------------------------------
def _patch_tags(monkeypatch, models=None, error=None):
    def fake_urlopen(req, timeout=0):
        if error:
            raise error
        return _Resp({"models": [{"name": n} for n in (models or [])]})

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)


def test_ollama_available_when_model_present(monkeypatch):
    monkeypatch.setenv("OLLAMA_MODEL", "llama3.2")
    _patch_tags(monkeypatch, ["llama3.2:latest"])
    r = ModelRouter()
    m = next(x for x in r.registry.models if x.provider == "ollama")
    assert r._available(m) is True


def test_ollama_model_tag_prefix_match(monkeypatch):
    # OLLAMA_MODEL=llama3.2 must match the concrete "llama3.2:latest" tag.
    monkeypatch.setenv("OLLAMA_MODEL", "llama3.2")
    _patch_tags(monkeypatch, ["qwen3:8b", "llama3.2:latest"])
    r = ModelRouter()
    m = next(x for x in r.registry.models if x.provider == "ollama")
    assert r._available(m) is True


def test_ollama_available_any_model_when_unset(monkeypatch):
    monkeypatch.delenv("OLLAMA_MODEL", raising=False)
    _patch_tags(monkeypatch, ["whatever:latest"])
    r = ModelRouter()
    m = next(x for x in r.registry.models if x.provider == "ollama")
    assert r._available(m) is True


def test_ollama_unavailable_when_model_missing(monkeypatch):
    monkeypatch.setenv("OLLAMA_MODEL", "llama3.2")
    _patch_tags(monkeypatch, ["qwen3:8b"])  # requested model not present
    r = ModelRouter()
    m = next(x for x in r.registry.models if x.provider == "ollama")
    assert r._available(m) is False


def test_ollama_unavailable_on_connection_refused(monkeypatch):
    _patch_tags(monkeypatch, error=ConnectionResetError("refused"))
    r = ModelRouter()
    m = next(x for x in r.registry.models if x.provider == "ollama")
    assert r._available(m) is False


def test_ollama_unavailable_on_empty_model_list(monkeypatch):
    monkeypatch.delenv("OLLAMA_MODEL", raising=False)
    _patch_tags(monkeypatch, [])
    r = ModelRouter()
    m = next(x for x in r.registry.models if x.provider == "ollama")
    assert r._available(m) is False


# --- completion -------------------------------------------------------------
def test_ollama_completion_posts_chat(monkeypatch):
    adapter = OllamaAdapter("http://ollama.test", "llama3.2")
    captured = {}

    def fake_open(req, timeout=0):
        captured["url"] = req.full_url
        captured["payload"] = json.loads(req.data.decode())
        return _Resp({"message": {"content": "hello"}})

    monkeypatch.setattr(adapter.opener, "open", fake_open)
    out = adapter.complete("hi")
    assert out.text == "hello"
    assert captured["url"] == "http://ollama.test/api/chat"
    assert captured["payload"]["model"] == "llama3.2"
    assert captured["payload"]["stream"] is False
    assert captured["payload"]["messages"] == [{"role": "user", "content": "hi"}]


def test_ollama_completion_malformed_response_raises(monkeypatch):
    adapter = OllamaAdapter("http://ollama.test", "llama3.2")
    monkeypatch.setattr(adapter.opener, "open", lambda req, timeout=0: _Resp({"unexpected": 1}))
    with pytest.raises(ProviderError):
        adapter.complete("hi")


def test_ollama_completion_timeout_raises(monkeypatch):
    adapter = OllamaAdapter("http://ollama.test", "llama3.2")

    def boom(req, timeout=0):
        raise TimeoutError("timed out")

    monkeypatch.setattr(adapter.opener, "open", boom)
    with pytest.raises(ProviderError):
        adapter.complete("hi")


def test_ollama_uses_proxy_free_opener_when_not_patched(monkeypatch):
    # In production urllib.request.urlopen is not patched, so _open must route
    # through the proxy-free opener (never through HTTP(S)_PROXY).
    monkeypatch.setenv("HTTP_PROXY", "http://should-not-be-used:3128")
    monkeypatch.setenv("HTTPS_PROXY", "http://should-not-be-used:3128")
    adapter = OllamaAdapter("http://127.0.0.1:11434", "llama3.2")
    used = {}

    def spy(req, timeout=0):
        used["opener"] = True
        return _Resp({"message": {"content": "ok"}})

    monkeypatch.setattr(adapter.opener, "open", spy)
    assert adapter.complete("hi").text == "ok"
    assert used.get("opener") is True


# --- router fallback + circuit breaker -------------------------------------
def test_router_selects_ollama_on_claude_weekly_limit():
    a = ModelCandidate("anthropic", "claude-code", {"executor"}, tool_capable=True, priority=1)
    o = ModelCandidate("ollama", "local", {"executor"}, free=True, tool_capable=True, priority=80)
    rt = ModelRouter(ModelRegistry([a, o]))
    rt._available = lambda m: True
    # Claude Code hits its weekly limit -> circuit opens -> ollama is chosen.
    rt.report_failure(a, error="You've hit your weekly limit")
    assert rt.circuit_view()["claude-code"]["state"] == "open"
    ranked = rt.fallback_policy("weekly_limit", "executor", exclude={"claude-code"})
    assert ranked and ranked[0].provider == "ollama"


def test_ollama_is_tool_capable_and_covers_agent_roles():
    m = next(x for x in ModelRegistry.default().models if x.provider == "ollama")
    assert m.tool_capable and m.free
    assert {"planner", "executor", "reviewer", "fixer", "tester",
            "architect", "researcher", "judge"} <= m.roles
