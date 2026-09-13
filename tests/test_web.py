"""Web tools: HTML stripping, DuckDuckGo result parsing, fetch guard."""
import pytest
from core import web

SAMPLE = (
    '<div class="results">'
    '<a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Fpage&rut=x">Example <b>Title</b></a>'
    '<a class="result__a" href="https://direct.test/x">Direct hit</a>'
    '</div>'
)


def test_strip_html_removes_tags_and_scripts():
    t = web.strip_html("<p>Hello <b>world</b></p><script>bad()</script>")
    assert "Hello world" in t and "bad" not in t


def test_parse_ddg_extracts_and_unwraps():
    r = web.parse_ddg(SAMPLE, limit=5)
    assert r[0]["url"] == "https://example.com/page"
    assert r[0]["title"] == "Example Title"
    assert r[1]["url"] == "https://direct.test/x"


def test_web_fetch_returns_text(monkeypatch):
    monkeypatch.setattr(web, "_get", lambda url, timeout=20: "<h1>Title</h1><p>Body text here</p>")
    r = web.web_fetch("https://example.com")
    assert r["url"] == "https://example.com" and "Body text here" in r["text"]


def test_web_fetch_rejects_non_http():
    with pytest.raises(ValueError):
        web.web_fetch("ftp://x/y")


def test_web_search_parses(monkeypatch):
    monkeypatch.setattr(web, "_get", lambda url, timeout=20: SAMPLE)
    r = web.web_search("q", limit=5)
    assert r["query"] == "q" and r["results"][0]["url"] == "https://example.com/page"


def test_executor_web_tools_wired(tmp_path, monkeypatch):
    from core.tool_executor import ToolExecutor
    monkeypatch.setattr("core.web.web_search", lambda q, limit=5: {"query": q, "results": [{"title": "t", "url": "u"}]})
    monkeypatch.setattr("core.web.web_fetch", lambda url: {"url": url, "text": "body", "truncated": False})
    ex = ToolExecutor(str(tmp_path))
    assert ex.execute("web_search", {"query": "x"})["results"][0]["url"] == "u"
    assert ex.execute("web_fetch", {"url": "https://a"})["text"] == "body"
