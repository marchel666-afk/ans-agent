from .types import ModelCandidate

class ModelRegistry:
    def __init__(self, models=None) -> None:
        # Optional seeding with an iterable of candidates keeps the registry
        # convenient to construct in tests and when composing custom pools,
        # while ``ModelRegistry()`` and ``ModelRegistry.default()`` keep working.
        self.models: list[ModelCandidate] = list(models) if models else []

    def register(self, candidate: ModelCandidate) -> None:
        self.models.append(candidate)

    def for_role(self, role: str) -> list[ModelCandidate]:
        return sorted((m for m in self.models if role in m.roles), key=lambda m: m.priority)

    ALL_ROLES = {"executor", "tester", "fixer", "planner", "architect", "reviewer", "researcher", "judge"}

    @classmethod
    def default(cls) -> "ModelRegistry":
        import os
        r = cls()
        # Local Claude Code CLI (dev machines only; the model name 'claude-code'
        # routes to the CLI adapter). Highest static priority when present.
        r.register(ModelCandidate("anthropic", "claude-code", set(cls.ALL_ROLES), tool_capable=True, priority=1))
        # Native Anthropic API (Claude) — used when ANTHROPIC_API_KEY is set.
        r.register(ModelCandidate("anthropic", os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-5"), set(cls.ALL_ROLES), tool_capable=True, priority=2))
        # Groq — free + very fast; good default executor when no premium key.
        r.register(ModelCandidate("groq", os.getenv("GROQ_MODEL", "openai/gpt-oss-20b"), set(cls.ALL_ROLES), tool_capable=True, priority=8))
        r.register(ModelCandidate("openai", "gpt", {"planner", "architect", "reviewer", "judge", "executor", "tester", "fixer"}, tool_capable=True, priority=5))
        r.register(ModelCandidate("google", "gemini", {"researcher", "planner", "reviewer", "judge", "executor"}, tool_capable=True, priority=10))
        r.register(ModelCandidate("openrouter", "openrouter/free", {"researcher", "reviewer", "planner", "executor"}, free=True, tool_capable=True, priority=50))
        r.register(ModelCandidate("ollama", "local", set(cls.ALL_ROLES), free=True, tool_capable=True, priority=80))
        return r
