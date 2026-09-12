from core.router import ModelRouter
from core.types import ModelCandidate


def candidate():
    return ModelCandidate("test","m",{"planner"},priority=50)


def test_failure_categories():
    r=ModelRouter()
    assert r.classify_failure("You've hit your weekly limit") [0] == "weekly_limit"
    assert r.classify_failure("HTTP 429 rate limit") [0] == "rate_limit"
    assert r.classify_failure("401 Unauthorized") [0] == "auth"
    assert r.classify_failure("request timed out") [0] == "timeout"


def test_weekly_limit_has_long_cooldown():
    r=ModelRouter()
    result=r.report_failure(candidate(),error="weekly usage limit reached")
    assert result["category"]=="weekly_limit"
    assert result["cooldown_seconds"]>=21600


def test_success_clears_cooldown():
    r=ModelRouter()
    m=candidate()
    r.report_failure(m,error="rate limit 429")
    assert m.model in r.failures
    r.report_success(m)
    assert m.model not in r.failures
