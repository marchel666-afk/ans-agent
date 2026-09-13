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

    @classmethod
    def default(cls) -> "ModelRegistry":
        r = cls()
        r.register(ModelCandidate("anthropic", "claude-code", {"executor", "tester", "fixer", "planner", "architect", "reviewer", "researcher", "judge"}, tool_capable=True, priority=1))
        r.register(ModelCandidate("openai", "gpt", {"planner", "architect", "reviewer", "judge"}, priority=5))
        r.register(ModelCandidate("google", "gemini", {"researcher", "planner", "reviewer"}, priority=10))
        r.register(ModelCandidate("openrouter", "openrouter/free", {"researcher", "reviewer", "planner"}, free=True, priority=50))
        r.register(ModelCandidate("ollama", "local", {"researcher", "planner", "architect", "reviewer", "judge", "executor", "tester", "fixer"}, free=True, tool_capable=True, priority=80))
        return r
