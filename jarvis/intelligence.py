"""JARVIS intelligence extensions: selective memory retrieval and live web research.

This module is installed by the local entrypoint so the large legacy core remains
backward-compatible. It adds one reasoning layer around the existing OpenAI
function-calling brain instead of creating a second AI runtime.
"""
from __future__ import annotations

import datetime
import html
import re
from html.parser import HTMLParser
from urllib.parse import parse_qs, unquote, urlencode, urlparse


class _SearchParser(HTMLParser):
    """Small dependency-free parser for DuckDuckGo HTML search results."""

    def __init__(self):
        super().__init__()
        self.results = []
        self._current = None
        self._in_title = False
        self._in_snippet = False
        self._title_parts = []
        self._snippet_parts = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        classes = set((attrs.get("class") or "").split())
        if tag == "a" and "result__a" in classes:
            self._current = {"url": attrs.get("href", ""), "title": "", "snippet": ""}
            self._title_parts = []
            self._in_title = True
        elif self._current and tag in {"a", "div", "span"} and "result__snippet" in classes:
            self._in_snippet = True
            self._snippet_parts = []

    def handle_data(self, data):
        if not self._current:
            return
        if self._in_title:
            self._title_parts.append(data)
        elif self._in_snippet:
            self._snippet_parts.append(data)

    def handle_endtag(self, tag):
        if self._in_title and tag == "a":
            self._current["title"] = " ".join("".join(self._title_parts).split())
            self._in_title = False
        elif self._in_snippet and tag in {"div", "span"}:
            self._current["snippet"] = " ".join("".join(self._snippet_parts).split())
            self._in_snippet = False
        elif self._current and tag == "a" and self._current.get("title"):
            self._finish()

    def _finish(self):
        result = self._current
        self._current = None
        if result.get("title") and result.get("url"):
            self.results.append(result)


def _clean_result_url(url: str) -> str:
    """Unwrap common DuckDuckGo redirect URLs."""
    if url.startswith("//"):
        url = "https:" + url
    try:
        parsed = urlparse(url)
        qs = parse_qs(parsed.query)
        if "uddg" in qs:
            return unquote(qs["uddg"][0])
    except Exception:
        pass
    return url


def web_research(query: str, max_results: int = 5) -> str:
    """Retrieve current web search results for the reasoning model.

    Unlike the legacy web_search tool, this does not merely open a browser. It
    returns titles, snippets and source URLs so the LLM can reason over current
    information before answering the user.
    """
    import requests

    query = (query or "").strip()
    if not query:
        return "No web-search query was supplied."
    max_results = max(1, min(int(max_results or 5), 8))

    url = "https://html.duckduckgo.com/html/?" + urlencode({"q": query})
    try:
        response = requests.get(
            url,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Jarvis/1.0"},
            timeout=8,
        )
        response.raise_for_status()
    except Exception as exc:
        return f"Live web search failed: {exc}"

    parser = _SearchParser()
    try:
        parser.feed(response.text)
    except Exception as exc:
        return f"Live web search parsing failed: {exc}"

    results = []
    seen = set()
    for item in parser.results:
        clean_url = _clean_result_url(item["url"])
        if not clean_url or clean_url in seen:
            continue
        seen.add(clean_url)
        results.append({
            "title": html.unescape(item["title"])[:240],
            "snippet": html.unescape(item.get("snippet", ""))[:600],
            "url": clean_url,
        })
        if len(results) >= max_results:
            break

    if not results:
        return f"No live search results were returned for: {query}"

    now = datetime.datetime.now().astimezone().isoformat(timespec="seconds")
    lines = [f"Live web results for: {query}", f"Retrieved: {now}"]
    for index, item in enumerate(results, 1):
        lines.append(
            f"{index}. {item['title']}\n"
            f"   {item['snippet']}\n"
            f"   Source: {item['url']}"
        )
    return "\n".join(lines)


def recall_personal_context(category: str = "", key: str = "") -> str:
    """Selectively retrieve persisted personal memory instead of dumping it all."""
    import jarvis.core as core

    category = (category or "").strip().lower()
    key = (key or "").strip().lower()
    allowed = {"profile", "preferences", "routines", "projects", "facts", "tasks"}
    if category and category not in allowed:
        return f"Unknown memory category. Use one of: {', '.join(sorted(allowed))}."

    memory = getattr(core, "MEMORY_DATA", {})
    categories = [category] if category else ["profile", "preferences", "routines", "projects", "facts", "tasks"]
    matches = []

    for cat in categories:
        data = memory.get(cat, {})
        if cat == "tasks":
            items = data if isinstance(data, list) else []
            for item in items:
                text = str(item.get("task", ""))
                if not key or key in text.lower():
                    matches.append(f"tasks: {item}")
            continue
        if not isinstance(data, dict):
            continue
        for name, value in data.items():
            if key and key not in str(name).lower() and key not in str(value).lower():
                continue
            matches.append(f"{cat}.{name}: {value}")

    if not matches:
        return "No matching personal memory was found."
    return "Relevant personal memory:\n" + "\n".join(matches[-12:])


def install(core) -> None:
    """Install the extensions into the existing core tool-calling runtime."""
    tool_names = {
        item.get("function", {}).get("name")
        for item in getattr(core, "TOOLS", [])
    }

    if "web_research" not in tool_names:
        core.TOOLS.append({
            "type": "function",
            "function": {
                "name": "web_research",
                "description": (
                    "Search the live web and return current source titles, snippets and URLs. "
                    "MUST use this for current/time-sensitive questions such as today's news, "
                    "current events, live information, recent updates, prices, weather or sports. "
                    "Do not use the browser-opening web_search tool when you need information to answer."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                        "max_results": {"type": "integer", "description": "1-8, default 5"},
                    },
                    "required": ["query"],
                },
            },
        })

    if "recall_personal_context" not in tool_names:
        core.TOOLS.append({
            "type": "function",
            "function": {
                "name": "recall_personal_context",
                "description": (
                    "Retrieve relevant persisted private user memory. Use this when the user asks "
                    "about their saved details, preferences, routines, projects or unfinished tasks. "
                    "Do not invent memories."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "category": {"type": "string", "enum": ["profile", "preferences", "routines", "projects", "facts", "tasks"]},
                        "key": {"type": "string", "description": "Optional keyword to narrow the retrieval"},
                    },
                },
            },
        })

    core.TOOL_FUNCTIONS["web_research"] = lambda args: web_research(
        args.get("query", ""), args.get("max_results", 5)
    )
    core.TOOL_FUNCTIONS["recall_personal_context"] = lambda args: recall_personal_context(
        args.get("category", ""), args.get("key", "")
    )
    core.SIMPLE_ACTION_TOOLS.discard("web_research")
    core.SIMPLE_ACTION_TOOLS.discard("recall_personal_context")

    core.NOVA_SYSTEM_PROMPT += (
        "\n\nINTELLIGENCE LAYER: You are the reasoning layer. Use function calling to act on the "
        "computer instead of merely describing actions. Use conversation history for immediate "
        "context. Use recall_personal_context for persisted personal details rather than assuming "
        "them. When the user asks for current or time-sensitive information, call web_research "
        "first, then answer from the returned sources. Never claim live knowledge without a live "
        "search result. Prefer one useful tool call over a chain of unnecessary questions."
    )

    # Keep the existing context snapshot lightweight. Persisted memory is now
    # retrieved on demand through recall_personal_context, reducing prompt size.
    original_snapshot = core.context_snapshot

    def compact_context_snapshot():
        try:
            import json
            context = json.loads(original_snapshot())
        except Exception:
            return original_snapshot()

        personal = context.pop("personal_memory", {})
        context["memory_available"] = {
            "categories": list(personal.keys()),
            "retrieval": "Use recall_personal_context when details are needed.",
        }
        context["time"] = datetime.datetime.now().astimezone().isoformat(timespec="seconds")
        return json.dumps(context, ensure_ascii=False)

    compact_context_snapshot._jarvis_intelligence_context = True
    core.context_snapshot = compact_context_snapshot
