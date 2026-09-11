from .registry import ModelRegistry
from .types import ModelCandidate

class ModelRouter:
    """Rule-based router. Provider adapters can be swapped without changing orchestration."""
    def __init__(self, registry: ModelRegistry | None = None) -> None:
        self.registry = registry or ModelRegistry.default()

    def choose(self, role: str, *, requires_tools: bool = False, prefer_free: bool = False) -> ModelCandidate:
        candidates = self.registry.for_role(role)
        if requires_tools:
            candidates = [m for m in candidates if m.tool_capable]
        if prefer_free:
            free = [m for m in candidates if m.free]
            if free:
                candidates = free
        if not candidates:
            raise RuntimeError(f"No model available for role={role!r}")
        return candidates[0]
