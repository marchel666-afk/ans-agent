from dataclasses import dataclass
from typing import Protocol

@dataclass
class ProviderResponse:
    text: str
    raw: object | None = None

class Provider(Protocol):
    name: str
    def complete(self, prompt: str, **kwargs) -> ProviderResponse: ...

class ProviderError(RuntimeError):
    pass

class FallbackProvider:
    def __init__(self, providers: list[Provider]):
        self.providers = providers

    def complete(self, prompt: str, **kwargs) -> ProviderResponse:
        errors = []
        for provider in self.providers:
            try:
                return provider.complete(prompt, **kwargs)
            except Exception as exc:
                errors.append(f"{getattr(provider, 'name', 'provider')}: {exc}")
        raise ProviderError("All providers failed: " + "; ".join(errors))
