"""Unified agent loop (Phase 1).

One continuous loop in a single thread: the model receives the task plus the
full running history and decides, each turn, whether to think, call tools, or
finish — instead of the old rigid planner→executor→reviewer→fixer pipeline.

Provider-neutral: uses adapter.chat() (native OpenAI/Anthropic tool-calling,
with a JSON-line fallback for CLI/Ollama), the shared tool catalogue, and the
existing ModelRouter for model selection + adaptive fallback.
"""
import json, time
from .adapters import ProviderError
from .tool_schema import READONLY

SYSTEM_PROMPT = (
    "Ты — ANS, автономный универсальный ИИ-агент. Решаешь ЛЮБЫЕ задачи "
    "(код, исследование, тексты, данные, работа с файлами) с помощью инструментов "
    "в изолированной рабочей области. Работаешь сам, до результата.\n\n"
    "Принципы:\n"
    "1. Сначала пойми задачу и осмотрись (list_files/read_file/search), потом действуй.\n"
    "2. Делай маленькими проверяемыми шагами; после правок — проверяй (terminal: тесты/запуск).\n"
    "3. Нужны свежие факты — web_search/web_fetch.\n"
    "4. Не выдумывай содержимое файлов — читай их.\n"
    "5. Отвечай и пиши итоги по-русски.\n"
    "6. Когда задача полностью выполнена — вызови finish с кратким понятным итогом.\n"
    "За один ход можешь вызвать один или несколько инструментов; опирайся на их результаты."
)


def _short(obj, n=1500):
    try:
        s = obj if isinstance(obj, str) else json.dumps(obj, ensure_ascii=False, default=str)
    except Exception:
        s = str(obj)
    return s[:n]


class AgentLoop:
    def __init__(self, router, adapters, executor, emit=None, approval=None,
                 session_id=None, job=None, job_manager=None, profile=None,
                 policy="balanced", budget=None, memory=None):
        self.router = router
        self.adapters = adapters
        self.executor = executor
        self.emit = emit or (lambda *a, **k: None)
        self.approval = approval
        self.session_id = session_id
        self.job = job
        self.job_manager = job_manager
        self.profile = profile
        self.policy = policy
        self.budget = budget
        self.memory = memory

    def _cancelled(self):
        return bool(getattr(getattr(self, "job", None), "cancel_requested", False))

    def _candidates(self, role="executor"):
        cands = self.router.policy_rank(role, self.policy, requires_tools=True, budget=self.budget)
        pref = getattr(self.profile, "executor", None) if self.profile else None
        if pref:
            cands = sorted(cands, key=lambda m: 0 if (m.model == pref or m.provider == pref) else 1)
        return cands

    def _chat(self, messages, role="executor"):
        """One model turn with adaptive provider fallback. Returns (reply, model)."""
        cands = self._candidates(role)
        if not cands:
            raise ProviderError("Нет доступной модели с поддержкой инструментов")
        errors, tried = [], set()
        while cands:
            m = cands.pop(0)
            if m.model in tried:
                continue
            tried.add(m.model)
            adapter = self.adapters.get(m.model) or self.adapters.get(m.provider)
            if not adapter or not hasattr(adapter, "chat"):
                errors.append(f"{m.provider}: адаптер недоступен")
                continue
            self.emit("provider.selected", m.provider + "/" + m.model, role=role,
                      score=self.router.score(m, role))
            started = time.time()
            try:
                reply = adapter.chat(messages, model=m.model, cwd=self.executor.ws.root)
                elapsed = time.time() - started
                self.router.report_success(m)
                self.router.record_task(m, role, True, elapsed)
                return reply, m
            except Exception as e:
                elapsed = time.time() - started
                err = str(e)[:200]
                failure = self.router.report_failure(m, error=err)
                self.router.record_task(m, role, False, elapsed)
                errors.append(f"{m.provider}: {err}")
                self.emit("provider.failed", err, provider=m.provider, model=m.model,
                          category=failure["category"], cooldown_seconds=failure["cooldown_seconds"])
                cands = [c for c in self.router.fallback_policy(failure["category"], role, self.policy, exclude=tried)]
        raise ProviderError("Все провайдеры недоступны: " + "; ".join(errors[:5]))

    def run(self, task, max_steps=40, role="executor"):
        context = ""
        if self.memory:
            try:
                context = self.memory.get_context()
            except Exception:
                context = ""
        user = task if not context else "ПАМЯТЬ ПРОЕКТА:\n" + context + "\n\nЗАДАЧА:\n" + task
        messages = [{"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user}]
        observations, completed = [], []
        summary, status = "", "max_steps"
        last_text = ""

        for step in range(1, max_steps + 1):
            if self._cancelled():
                status = "cancelled"; summary = "Остановлено пользователем."; break

            reply, model = self._chat(messages, role=role)
            text = (reply.get("text") or "").strip()
            calls = reply.get("tool_calls") or []
            last_text = text or last_text
            if text:
                self.emit("assistant", text, step=step, model=model.provider + "/" + model.model)

            # Record the assistant turn (with any tool calls) in history.
            messages.append({"role": "assistant", "content": text,
                             "tool_calls": [{"id": c["id"], "name": c["name"], "args": c.get("args") or {}} for c in calls]})

            if not calls:
                # No tool call -> the model's message is the final answer.
                status = "completed"; summary = text or summary; break

            finished = False
            for c in calls:
                name, args, cid = c.get("name"), (c.get("args") or {}), c.get("id")
                if name in ("finish", "done", "final"):
                    summary = args.get("summary") or args.get("result") or text or "Готово."
                    status = "completed"; finished = True
                    messages.append({"role": "tool", "tool_call_id": cid, "name": name, "content": "OK"})
                    break

                # Approval gate for state-changing tools.
                if self.approval and name not in READONLY:
                    if not self.approval.request(self.session_id, name, args):
                        self.emit("approval.waiting", f"Требуется подтверждение: {name}", tool=name, args=args)
                        if self.job is not None and self.job_manager:
                            self.job_manager.set_waiting(self.job)
                        if not self.approval.wait_for(self.session_id, name, args):
                            result = {"ok": False, "error": "отклонено пользователем или таймаут"}
                            self.emit("tool.result", name, result=result)
                            messages.append({"role": "tool", "tool_call_id": cid, "name": name, "content": _short(result)})
                            continue
                        if self.job is not None and self.job_manager:
                            self.job_manager.set_running(self.job)

                self.emit("tool.call", name, args=args, step=step)
                try:
                    result = self.executor.execute(name, args)
                except Exception as e:
                    result = {"ok": False, "error": str(e)[:500]}
                self.emit("tool.result", name, result=result)
                observations.append(f"{name}({_short(args,200)}) → {_short(result,400)}")
                if name == "write_file" and result.get("ok"):
                    completed.append("Записан файл " + str(args.get("path", "")))
                messages.append({"role": "tool", "tool_call_id": cid, "name": name, "content": _short(result, 4000)})

            if finished:
                break
            if self.budget is not None and self.budget <= 0:
                status = "budget"; break

        if status == "max_steps" and not summary:
            summary = last_text or "Достигнут лимит шагов."
        if self.memory and completed:
            try:
                self.memory.remember_result(task, "\n".join(observations[-8:]))
            except Exception:
                pass
        return {"status": status, "summary": summary, "iterations": step,
                "completed": completed, "observations": observations, "plan": []}
