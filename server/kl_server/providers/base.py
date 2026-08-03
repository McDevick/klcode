from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class ProviderRequest:
    messages: list[dict[str, str]]
    model: str
    max_tokens: int = 2048


@dataclass(frozen=True)
class ProviderResponse:
    text: str
    raw: dict | None = None


class Provider(Protocol):
    async def complete(self, request: ProviderRequest) -> ProviderResponse:
        ...
