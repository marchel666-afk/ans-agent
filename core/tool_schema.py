"""Single source of truth for the agent's tool catalogue.

Tool names/args match ToolExecutor.execute. We emit the catalogue in two wire
formats — OpenAI (`tools`/`tool_calls`) and Anthropic (`tools`/`tool_use`) — so
every provider can use native function-calling; providers without it fall back
to a JSON-line protocol built from the same catalogue (see adapters).
"""

# name -> (description, json-schema properties, required[])
TOOLS = {
    "read_file": ("Прочитать файл в рабочей области.",
                  {"path": {"type": "string"}}, ["path"]),
    "write_file": ("Создать или полностью перезаписать файл.",
                   {"path": {"type": "string"}, "content": {"type": "string"}}, ["path", "content"]),
    "append_file": ("Дописать текст в конец файла.",
                    {"path": {"type": "string"}, "content": {"type": "string"}}, ["path", "content"]),
    "replace_in_file": ("Точечная правка: заменить фрагмент 'old' на 'new' (old должен встречаться ровно один раз).",
                        {"path": {"type": "string"}, "old": {"type": "string"}, "new": {"type": "string"}}, ["path", "old", "new"]),
    "list_files": ("Список файлов рабочей области (или подпапки).",
                   {"path": {"type": "string"}}, []),
    "search": ("Найти подстроку в файлах рабочей области.",
               {"query": {"type": "string"}, "path": {"type": "string"}}, ["query"]),
    "web_search": ("Поиск в интернете, возвращает ссылки и сниппеты.",
                   {"query": {"type": "string"}, "limit": {"type": "integer"}}, ["query"]),
    "web_fetch": ("Скачать веб-страницу как текст.",
                  {"url": {"type": "string"}}, ["url"]),
    "terminal": ("Выполнить shell-команду в рабочей области (timeout сек, макс 300).",
                 {"command": {"type": "string"}, "timeout": {"type": "integer"}}, ["command"]),
    "git_status": ("git status --short.", {}, []),
    "git_diff": ("git diff.", {}, []),
    "git_branch": ("Текущая git-ветка.", {}, []),
    "git_log": ("Последние коммиты.", {}, []),
    "finish": ("Завершить задачу. summary — краткий понятный итог для пользователя на русском.",
               {"summary": {"type": "string"}}, ["summary"]),
}

# Tools that only read / are safe to auto-run even under stricter policies.
READONLY = {"read_file", "list_files", "search", "web_search", "web_fetch",
            "git_status", "git_diff", "git_branch", "git_log", "finish"}


def _schema(props, required):
    return {"type": "object", "properties": props, "required": required}


def openai_tools():
    return [{"type": "function", "function": {
        "name": n, "description": d, "parameters": _schema(p, r)}}
        for n, (d, p, r) in TOOLS.items()]


def anthropic_tools():
    return [{"name": n, "description": d, "input_schema": _schema(p, r)}
            for n, (d, p, r) in TOOLS.items()]


def catalogue_text():
    """Plain-text tool list for the JSON-line fallback (Claude Code / Ollama)."""
    lines = []
    for n, (d, p, r) in TOOLS.items():
        args = ", ".join(p.keys())
        lines.append(f"- {n}({args}) — {d}")
    return "\n".join(lines)
