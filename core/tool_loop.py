import json, re

TOOLS = (
    "Ты — автономный универсальный ИИ-агент. Ты решаешь ЛЮБЫЕ задачи "
    "(код, исследование, тексты, анализ данных, работа с файлами), "
    "используя инструменты внутри изолированной рабочей области.\n"
    "Отвечай пользователю по-русски.\n\n"
    "Доступные инструменты (вызывай РОВНО ОДИН за шаг, выводя одну строку JSON):\n"
    "- read_file {path}\n"
    "- write_file {path, content}   # создать или перезаписать файл целиком\n"
    "- replace_in_file {path, old, new}   # точечная правка; 'old' должен встречаться ровно один раз\n"
    "- append_file {path, content}\n"
    "- list_files {path?}\n"
    "- search {query, path?}\n"
    "- web_search {query, limit?}   # поиск в интернете\n"
    "- web_fetch {url}   # скачать веб-страницу как текст\n"
    "- terminal {command, timeout?}\n"
    "- git_status {}\n- git_diff {}\n- git_log {}\n"
    "- finish {summary}   # вызови, когда шаг выполнен; summary — итог по-русски\n\n"
    "Правила: коротко подумай, затем выведи ровно одну строку JSON вида "
    '{\"tool\":\"read_file\",\"args\":{\"path\":\"app.py\"}}. '
    "Опирайся на результаты в PROGRESS, чтобы выбрать следующее действие. "
    "Если для задачи нужны свежие факты — используй web_search/web_fetch. "
    "Когда задача выполнена, вызови finish с кратким понятным итогом на русском."
)


def _extract_json(text):
    """Pull the first parseable JSON object out of a model response."""
    for line in text.splitlines():
        line = line.strip().strip("`").strip()
        if line.startswith("{") and line.endswith("}"):
            try:
                return json.loads(line)
            except Exception:
                pass
    m = re.search(r"\{.*\}", text, re.S)
    if m:
        try:
            return json.loads(m.group(0))
        except Exception:
            pass
    return None


class ToolLoop:
    def __init__(self, adapter, executor, emit=None, approval=None, session_id=None):
        self.adapter = adapter
        self.executor = executor
        self.emit = emit or (lambda *a, **k: None)
        self.approval = approval
        self.session_id = session_id

    def run(self, prompt, max_steps=20):
        system = prompt + "\n\n" + TOOLS
        transcript = []  # accumulated step history so the agent remembers its work
        for i in range(max_steps):
            if getattr(getattr(self.executor, "job", None), "cancel_requested", False):
                return "CANCELLED_BY_USER"
            convo = system
            if transcript:
                convo += "\n\nPROGRESS SO FAR:\n" + "\n".join(transcript[-40:])
            convo += "\n\nNext action (one JSON line), or finish when done:"
            answer = self.adapter.complete(convo, cwd=str(self.executor.ws.root)).text.strip()
            obj = _extract_json(answer)
            if not obj or "tool" not in obj:
                # No tool call -> treat the plain answer as the final result.
                return answer
            name, args = obj["tool"], obj.get("args", {}) or {}
            if name in ("finish", "done", "final"):
                return args.get("summary") or args.get("result") or args.get("text") or "Task step completed."
            if self.approval and not self.approval.request(self.session_id, name, args):
                self.emit("approval.waiting", f"Waiting for approval: {name}", tool=name, args=args)
                if getattr(self.executor, "job", None) and self.executor.manager:
                    self.executor.manager.set_waiting(self.executor.job)
                if not self.approval.wait_for(self.session_id, name, args):
                    return "APPROVAL_DENIED_OR_TIMEOUT: " + name
                if getattr(self.executor, "job", None) and self.executor.manager:
                    self.executor.manager.set_running(self.executor.job)
            self.emit("tool.call", name, args=args)
            try:
                result = self.executor.execute(name, args)
            except Exception as e:
                result = {"ok": False, "error": str(e)}
            self.emit("tool.result", name, result=result)
            transcript.append(
                f"STEP {i+1}: {name}({json.dumps(args, ensure_ascii=False)[:400]}) -> "
                + json.dumps(result, ensure_ascii=False)[:1500]
            )
        return "Reached maximum steps. Progress:\n" + "\n".join(transcript[-6:])
