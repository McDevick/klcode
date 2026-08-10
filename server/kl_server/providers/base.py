from dataclasses import dataclass, field
from typing import Protocol


@dataclass(frozen=True)
class ProviderToolCall:
    """原生 tool calling 的一次工具调用（OpenAI 格式）。"""

    id: str
    name: str
    arguments: str  # JSON 字符串


@dataclass(frozen=True)
class ProviderRequest:
    messages: list[dict]
    model: str
    max_tokens: int = 2048
    tools: list[dict] | None = None  # OpenAI tools 参数（type: function）


@dataclass(frozen=True)
class ProviderResponse:
    text: str  # 模型说的人话（content）；无 tool_calls 时即最终回答
    raw: dict | None = None
    tool_calls: list[ProviderToolCall] | None = None
    finish_reason: str | None = None


class Provider(Protocol):
    async def complete(self, request: ProviderRequest) -> ProviderResponse:
        ...
