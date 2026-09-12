from core.router import ModelRouter

def test_executor():
    m=ModelRouter().choose("executor",requires_tools=True)
    assert m.provider == "anthropic"

def test_free():
    assert ModelRouter().choose("researcher",prefer_free=True).free


def test_claude_fallback_for_planner(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    router=ModelRouter()
    monkeypatch.setattr(router, "_claude_cli_available", lambda: True)
    m=router.choose("planner")
    assert m.provider == "anthropic"
    assert m.model == "claude-code"
