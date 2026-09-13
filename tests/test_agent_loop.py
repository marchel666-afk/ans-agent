"""Agent tool loop: history accumulation, finish, robust parsing, search tool."""
from core.tool_loop import ToolLoop, _extract_json
from core.tool_executor import ToolExecutor


class ScriptAdapter:
    def __init__(self, script):
        self.script = script
        self.calls = 0
        self.prompts = []

    def complete(self, prompt, **k):
        self.prompts.append(prompt)
        r = self.script[min(self.calls, len(self.script) - 1)]
        self.calls += 1
        return type("R", (), {"text": r})()


def test_loop_accumulates_history_and_finishes(tmp_path):
    (tmp_path / "note.txt").write_text("hello world", encoding="utf-8")
    ex = ToolExecutor(str(tmp_path))
    adapter = ScriptAdapter([
        '{"tool":"list_files","args":{}}',
        '{"tool":"search","args":{"query":"hello"}}',
        '{"tool":"finish","args":{"summary":"done: found hello"}}',
    ])
    events = []
    loop = ToolLoop(adapter, ex, emit=lambda k, m=None, **d: events.append(k))
    out = loop.run("find hello", max_steps=10)
    assert out == "done: found hello"
    assert adapter.calls == 3
    # third prompt must carry the accumulated progress of the first two steps
    assert "PROGRESS SO FAR" in adapter.prompts[2]
    assert "list_files" in adapter.prompts[2] and "search" in adapter.prompts[2]
    assert "tool.call" in events and "tool.result" in events


def test_loop_returns_plain_answer_when_no_tool(tmp_path):
    ex = ToolExecutor(str(tmp_path))
    out = ToolLoop(ScriptAdapter(["Just a plain answer, no tools needed."]), ex).run("hi")
    assert out == "Just a plain answer, no tools needed."


def test_loop_parses_json_after_prose(tmp_path):
    ex = ToolExecutor(str(tmp_path))
    out = ToolLoop(ScriptAdapter(['Sure, done.\n{"tool":"finish","args":{"summary":"ok"}}']), ex).run("hi")
    assert out == "ok"


def test_loop_stops_at_max_steps(tmp_path):
    ex = ToolExecutor(str(tmp_path))
    # always asks to list files, never finishes
    out = ToolLoop(ScriptAdapter(['{"tool":"list_files","args":{}}']), ex).run("loop", max_steps=3)
    assert "maximum steps" in out.lower()


def test_extract_json_variants():
    assert _extract_json('{"tool":"x"}')["tool"] == "x"
    assert _extract_json('blah\n{"tool":"y","args":{}}\nmore')["tool"] == "y"
    assert _extract_json("no json here") is None


def test_search_tool(tmp_path):
    (tmp_path / "a.py").write_text("alpha\nneedle here\n", encoding="utf-8")
    (tmp_path / "b.txt").write_text("nothing", encoding="utf-8")
    ex = ToolExecutor(str(tmp_path))
    res = ex.execute("search", {"query": "needle"})
    assert res["ok"] and len(res["hits"]) == 1
    assert res["hits"][0]["file"] == "a.py" and res["hits"][0]["line"] == 2


def test_replace_in_file_tool(tmp_path):
    (tmp_path / "c.py").write_text("def add(a,b):\n    return a+b\n", encoding="utf-8")
    ex = ToolExecutor(str(tmp_path))
    res = ex.execute("replace_in_file", {"path": "c.py", "old": "return a+b", "new": "\"\"\"sum\"\"\"\n    return a+b"})
    assert res["ok"] and res["replaced"] == 1
    assert '"""sum"""' in (tmp_path / "c.py").read_text()


def test_replace_in_file_rejects_ambiguous(tmp_path):
    import pytest
    (tmp_path / "d.txt").write_text("x\nx\n", encoding="utf-8")
    ex = ToolExecutor(str(tmp_path))
    # executor raises; the ToolLoop converts this to {ok:False,error} for the model.
    with pytest.raises(ValueError, match="unique"):
        ex.execute("replace_in_file", {"path": "d.txt", "old": "x", "new": "y"})



def test_append_file_tool(tmp_path):
    ex = ToolExecutor(str(tmp_path))
    ex.execute("append_file", {"path": "log.txt", "content": "line1\n"})
    ex.execute("append_file", {"path": "log.txt", "content": "line2\n"})
    assert (tmp_path / "log.txt").read_text() == "line1\nline2\n"
