"""SessionStore persistence must tolerate non-string event messages
(e.g. the task.graph snapshot emitted during an agent run)."""
from core.session import SessionStore


def test_emit_non_string_message_persists(tmp_path):
    db = str(tmp_path / "s.db")
    st = SessionStore(db)
    s = st.create("task", "agent")
    # A list message (as orchestrator emits for task.graph) must not crash SQLite.
    st.emit(s.id, "task.graph", [{"id": "n1", "title": "step", "status": "todo"}])
    st.emit(s.id, "run.completed", "done")
    st.sessions.clear()  # force reconstruction from the database
    got = st.get(s.id)
    kinds = [e["kind"] for e in got.events]
    assert "task.graph" in kinds and "run.completed" in kinds


def test_project_memory_remember_result(tmp_path):
    from core.memory import ProjectMemory
    st = SessionStore(str(tmp_path / "m.db"))
    mem = ProjectMemory(st, "default")
    mem.remember_result("do X", "the final result")
    assert "the final result" in mem.get_context()
