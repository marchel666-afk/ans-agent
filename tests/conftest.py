"""Test isolation.

Runtime state (router health/stats, sessions, jobs) is persisted in SQLite.
Without isolation, tests share ``data/*.db`` and leak provider cooldowns and
stats across runs, making routing tests order- and history-dependent. This
autouse fixture points every DB path at a per-test temp directory so each test
starts from a clean, deterministic state.
"""
import pytest


@pytest.fixture(autouse=True)
def _isolate_runtime_state(tmp_path, monkeypatch):
    monkeypatch.setenv("ANS_ROUTER_DB", str(tmp_path / "router_stats.db"))
    monkeypatch.setenv("ANS_DB", str(tmp_path / "ans.db"))
    yield
