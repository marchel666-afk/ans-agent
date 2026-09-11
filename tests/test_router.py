from core.router import ModelRouter

def test_executor():
    m=ModelRouter().choose("executor",requires_tools=True)
    assert m.provider == "anthropic"

def test_free():
    assert ModelRouter().choose("researcher",prefer_free=True).free
