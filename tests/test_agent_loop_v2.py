"""Tests for the unified agent loop (Phase 1) and native tool-calling."""
import json
from core import adapters as A
from core.agent_loop import AgentLoop
from core.tool_executor import ToolExecutor
from core.router import ModelRouter
from core.registry import ModelRegistry
from core.types import ModelCandidate


def test_openai_chat_parses_tool_calls(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "k")
    resp = {"choices": [{"message": {"content": "думаю",
            "tool_calls": [{"id": "c1", "function": {"name": "list_files", "arguments": "{}"}}]}}]}
    class R:
        def read(self): return json.dumps(resp).encode()
        def __enter__(self): return self
        def __exit__(self, *a): return False
    monkeypatch.setattr(A.urllib.request, "urlopen", lambda req, timeout=0: R())
    ad = A.OpenAICompatibleAdapter("openai", "https://api.openai.com/v1", "OPENAI_API_KEY", "gpt-x")
    out = ad.chat([{"role": "user", "content": "покажи файлы"}])
    assert out["text"] == "думаю"
    assert out["tool_calls"][0]["name"] == "list_files"
    assert out["tool_calls"][0]["id"] == "c1"


def test_to_anthropic_groups_tool_results():
    msgs = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "", "tool_calls": [{"id": "t1", "name": "list_files", "args": {}}]},
        {"role": "tool", "tool_call_id": "t1", "name": "list_files", "content": "[]"},
    ]
    system, out = A._to_anthropic(msgs)
    assert system == "sys"
    assert out[0]["role"] == "user"
    assert out[1]["role"] == "assistant"
    assert any(b["type"] == "tool_use" for b in out[1]["content"])
    assert out[2]["role"] == "user" and out[2]["content"][0]["type"] == "tool_result"


def _router(tmp_path):
    rt = ModelRouter(ModelRegistry.default())
    rt.db = str(tmp_path / "r.db")
    rt._available = lambda m: True
    rt.policy_rank = lambda role, *a, **k: [ModelCandidate("p", "m", {"executor"}, tool_capable=True, priority=1)]
    return rt


def test_agent_loop_runs_tool_then_finishes(tmp_path):
    calls = {"n": 0}
    class FakeAdapter:
        def chat(self, messages, **kwargs):
            calls["n"] += 1
            if calls["n"] == 1:
                return {"text": "создаю файл", "tool_calls": [
                    {"id": "c1", "name": "write_file", "args": {"path": "hello.txt", "content": "привет"}}]}
            return {"text": "готово", "tool_calls": [
                {"id": "c2", "name": "finish", "args": {"summary": "Файл создан."}}]}
    ex = ToolExecutor(str(tmp_path))
    loop = AgentLoop(_router(tmp_path), {"m": FakeAdapter()}, ex, emit=lambda *a, **k: None)
    res = loop.run("создай файл hello.txt", max_steps=10)
    assert res["status"] == "completed"
    assert res["summary"] == "Файл создан."
    assert (tmp_path / "hello.txt").read_text(encoding="utf-8") == "привет"


def test_agent_loop_plain_answer_finishes(tmp_path):
    class FakeAdapter:
        def chat(self, messages, **kwargs):
            return {"text": "Ответ без инструментов.", "tool_calls": []}
    ex = ToolExecutor(str(tmp_path))
    loop = AgentLoop(_router(tmp_path), {"m": FakeAdapter()}, ex, emit=lambda *a, **k: None)
    res = loop.run("привет", max_steps=5)
    assert res["status"] == "completed"
    assert "без инструментов" in res["summary"]


def test_agent_loop_falls_back_across_providers(tmp_path):
    rt = ModelRouter(ModelRegistry.default())
    rt.db = str(tmp_path / "r.db"); rt._available = lambda m: True
    rt.policy_rank = lambda role, *a, **k: [
        ModelCandidate("bad", "b", {"executor"}, tool_capable=True, priority=1),
        ModelCandidate("good", "g", {"executor"}, tool_capable=True, priority=2)]
    rt.fallback_policy = lambda cat, role, policy, exclude=None: [
        ModelCandidate("good", "g", {"executor"}, tool_capable=True, priority=2)]
    class Bad:
        def chat(self, messages, **kwargs): raise RuntimeError("boom")
    class Good:
        def chat(self, messages, **kwargs): return {"text": "ок", "tool_calls": [{"id": "c", "name": "finish", "args": {"summary": "done"}}]}
    ex = ToolExecutor(str(tmp_path))
    loop = AgentLoop(rt, {"b": Bad(), "g": Good()}, ex, emit=lambda *a, **k: None)
    res = loop.run("сделай", max_steps=5)
    assert res["status"] == "completed" and res["summary"] == "done"
