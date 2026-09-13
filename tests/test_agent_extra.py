"""Cancellation, final summary, and per-task workspace."""
import app
from fastapi.testclient import TestClient
from core.orchestrator import Orchestrator
from core.router import ModelRouter
from core.tool_loop import ToolLoop
from core.tool_executor import ToolExecutor
from core.types import ModelCandidate

client = TestClient(app.app)


class _AllRoles(ModelRouter):
    def rank(self, role, requires_tools=False, **k):
        return [ModelCandidate("x", "m", {"planner", "executor", "reviewer", "fixer"}, tool_capable=True, priority=1)]


def _mk(tmp_path, adapter):
    o = Orchestrator(workspace=str(tmp_path))
    o.router = _AllRoles(); o.router.db = str(tmp_path / "r.db"); o.router._available = lambda m: True
    o.adapters = {"m": adapter}; o.emit = lambda *a, **k: None; o.profile = None
    return o


def test_tool_loop_cancelled(tmp_path):
    ex = ToolExecutor(str(tmp_path)); ex.job = type("J", (), {"cancel_requested": True})()

    class A:
        def complete(self, p, **k): return type("R", (), {"text": '{"tool":"list_files","args":{}}'})()

    assert ToolLoop(A(), ex).run("x") == "CANCELLED_BY_USER"


def test_orchestrator_cancels_before_step(tmp_path):
    class A:
        def complete(self, p, **k): return type("R", (), {"text": "1. do thing"})()

    o = _mk(tmp_path, A())
    o.job = type("J", (), {"cancel_requested": True, "attempts": []})(); o.job_manager = None
    res = o.run("t", "agent", 3)
    assert res["status"] == "cancelled"


def test_orchestrator_returns_summary(tmp_path, monkeypatch):
    class A:
        def complete(self, p, **k):
            if "пошаговый план" in p:
                t = "1. only step"
            elif "PASS" in p and "FAIL" in p:
                t = "PASS looks good"
            else:
                t = "Итог: задача выполнена, файл обновлён."
            return type("R", (), {"text": t})()

    o = _mk(tmp_path, A())
    o.job = None; o.job_manager = None
    monkeypatch.setattr("core.orchestrator.ToolLoop", lambda *a, **k: type("L", (), {"run": lambda self, *a, **k: "did the step"})())
    res = o.run("t", "agent", 1)
    assert res["status"] == "completed"
    assert res.get("summary") and "Итог" in res["summary"]


def test_run_uses_task_workspace(monkeypatch):
    monkeypatch.setattr(app, "AUTH_TOKEN", "tok")
    cap = {}

    class FakeOrch:
        def __init__(self, router, workspace, **k): cap["ws"] = workspace; self.job_manager = None; self.job = None
        def run(self, *a, **k): return {"status": "completed", "completed": [], "observations": [], "iterations": 0, "summary": ""}

    monkeypatch.setattr(app, "Orchestrator", FakeOrch)
    r = client.post("/run", headers={"Authorization": "Bearer tok"}, json={"task": "t", "mode": "agent", "workspace": "proj1"})
    assert r.status_code == 200
    assert cap["ws"].replace("\\", "/").endswith("/proj1")


def test_run_workspace_blocks_traversal(monkeypatch):
    monkeypatch.setattr(app, "AUTH_TOKEN", "tok")
    cap = {}

    class FakeOrch:
        def __init__(self, router, workspace, **k): cap["ws"] = workspace; self.job_manager = None; self.job = None
        def run(self, *a, **k): return {"status": "completed", "completed": [], "observations": [], "iterations": 0}

    monkeypatch.setattr(app, "Orchestrator", FakeOrch)
    client.post("/run", headers={"Authorization": "Bearer tok"}, json={"task": "t", "workspace": "../../etc"})
    assert ".." not in cap["ws"]
