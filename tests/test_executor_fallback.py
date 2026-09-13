from core.orchestrator import Orchestrator
from core.router import ModelRouter
from core.types import ModelCandidate


def test_executor_provider_fallback(monkeypatch, tmp_path):
    orch = Orchestrator(workspace=str(tmp_path))
    class FakeAdapter:
        def __init__(self, text=None, error=None):
            self.text, self.error = text, error
        def complete(self, prompt="", **kwargs):
            if self.error:
                raise RuntimeError(self.error)
            text = self.text
            if "пошаговый план" in prompt:
                text = "1. create file"
            elif "PASS" in prompt and "FAIL" in prompt:
                text = "PASS"
            return type("R", (), {"text": text})()
    class FakeLoop:
        def __init__(self, adapter, executor, **kwargs):
            self.adapter = adapter
        def run(self, *args, **kwargs):
            return self.adapter.complete("").text
    class FakeRouter(ModelRouter):
        # Uses the real router interface (policy_rank/score/cost_estimate/reporting)
        # while pinning the candidate list so the executor fallback path from a
        # weekly-limited primary to the backup provider is exercised directly.
        def rank(self, role, requires_tools=False, **kwargs):
            return [
                ModelCandidate("anthropic", "claude-code", {"executor"}, tool_capable=True, priority=1),
                ModelCandidate("openrouter", "backup", {"executor"}, tool_capable=True, priority=2),
            ]
    orch.router = FakeRouter()
    orch.router.db = str(tmp_path / "router.db")
    orch.adapters = {
        "claude-code": FakeAdapter(error="weekly limit"),
        "openrouter": FakeAdapter(text="backup executed"),
    }
    monkeypatch.setattr("core.orchestrator.ToolLoop", FakeLoop)
    orch.emit = lambda *a, **k: None
    orch.profile = None
    result = orch.run("create a file", "agent", 1)
    assert result["status"] == "completed"
    assert any("backup executed" in x for x in result["observations"])
