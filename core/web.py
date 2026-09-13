"""Lightweight web tools for the agent: fetch a page as text, and search.

No API keys required. `web_search` uses DuckDuckGo's HTML endpoint and parses
result links; `web_fetch` downloads a URL and strips it to readable text.
Network access follows the host environment (honours HTTP(S)_PROXY via urllib).
"""
import html
import re
import urllib.parse
import urllib.request

_UA = {"User-Agent": "Mozilla/5.0 (compatible; ANS-Agent/1.0)"}


def _get(url, timeout=20, max_bytes=2_000_000):
    req = urllib.request.Request(url, headers=_UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read(max_bytes)
        enc = (r.headers.get_content_charset() or "utf-8")
    return raw.decode(enc, "replace")


def strip_html(h):
    h = re.sub(r"(?is)<(script|style|noscript|template)[^>]*>.*?</\1>", " ", h)
    h = re.sub(r"(?s)<br\s*/?>", "\n", h)
    h = re.sub(r"(?s)</(p|div|li|h[1-6]|tr)>", "\n", h)
    h = re.sub(r"(?s)<[^>]+>", " ", h)
    h = html.unescape(h)
    h = re.sub(r"[ \t\r\f]+", " ", h)
    h = re.sub(r"\n[ \t]*\n\s*", "\n\n", h)
    return h.strip()


def web_fetch(url, timeout=20, max_chars=8000):
    if not re.match(r"^https?://", url or "", re.I):
        raise ValueError("only http(s) URLs are allowed")
    text = strip_html(_get(url, timeout))
    return {"url": url, "text": text[:max_chars], "truncated": len(text) > max_chars}


def web_search(query, limit=5, timeout=20):
    page = _get("https://html.duckduckgo.com/html/?" + urllib.parse.urlencode({"q": query}), timeout)
    return {"query": query, "results": parse_ddg(page, limit)}


def parse_ddg(page, limit=5):
    results = []
    for m in re.finditer(r'<a[^>]+class="[^"]*result__a[^"]*"[^>]+href="([^"]+)"[^>]*>(.*?)</a>', page, re.S):
        href = html.unescape(m.group(1))
        mm = re.search(r"[?&]uddg=([^&]+)", href)
        if mm:
            href = urllib.parse.unquote(mm.group(1))
        title = strip_html(m.group(2))
        if title:
            results.append({"title": title[:200], "url": href})
        if len(results) >= limit:
            break
    return results
