from .types import ModelCandidate

class ModelRegistry:
    def __init__(self) -> None:
        self.models: list[ModelCandidate] = []

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
        r.register(ModelCandidate("ollama", "local", {"researcher", "planner", "reviewer"}, free=True, priority=80))
        return r
