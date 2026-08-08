import httpx
import openai

from kl_server.providers.base import (
    ProviderRequest,
    ProviderResponse,
    ProviderToolCall,
)


class ProviderError(RuntimeError):
    pass


class OpenAICompatibleProvider:
    def __init__(
        self,
        base_url: str,
        api_key: str | None,
        model: str,
        client: httpx.AsyncClient | None = None,
        timeout: float = 120.0,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self._owns_client = client is None
        self.client = client or httpx.AsyncClient(timeout=timeout)
        self.openai = openai.AsyncOpenAI(
            api_key=api_key or "not-needed",
            base_url=base_url,
            timeout=timeout,
            http_client=self.client,
        )

    def set_api_key(self, api_key: str | None) -> None:
        self.api_key = api_key
        self.openai.api_key = api_key or "not-needed"

    async def complete(self, request: ProviderRequest) -> ProviderResponse:
        model = request.model or self.model
        kwargs: dict = {
            "model": model,
            "messages": [self._normalize_message(message) for message in request.messages],
            "max_tokens": request.max_tokens,
        }
        if request.tools:
            kwargs["tools"] = request.tools
            kwargs["tool_choice"] = "auto"
        try:
            response = await self.openai.chat.completions.create(**kwargs)
        except openai.APIStatusError as exc:
            detail = exc.body if exc.body is not None else exc.message
            raise ProviderError(
                f"provider http error: {exc.status_code}: {detail}"
            ) from exc
        except openai.APITimeoutError as exc:
            raise ProviderError("provider timeout") from exc
        except openai.OpenAIError as exc:
            raise ProviderError(f"provider error: {exc}") from exc

        if not response.choices:
            raise ProviderError("unexpected provider response")
        message = response.choices[0].message
        content = message.content if isinstance(message.content, str) else ""
        if not content and isinstance(message.reasoning_content, str):
            content = message.reasoning_content
        tool_calls: list[ProviderToolCall] | None = None
        if message.tool_calls:
            tool_calls = []
            for call in message.tool_calls:
                function = call.function
                if function is None:
                    continue
                tool_calls.append(
                    ProviderToolCall(
                        id=call.id or "",
                        name=function.name or "",
                        arguments=function.arguments or "{}",
                    )
                )
            if not tool_calls:
                tool_calls = None
        return ProviderResponse(
            text=content,
            raw=response.model_dump(),
            tool_calls=tool_calls,
            finish_reason=response.choices[0].finish_reason,
        )

    @staticmethod
    def _normalize_message(message: dict) -> dict:
        # 防御映射：历史遗留的 feedback 角色（AgentLoop 现在直接构造 user
        # 消息，但外部调用方可能仍传 feedback）；tool 角色按原生格式原样透传。
        if message.get("role") == "feedback":
            return {"role": "user", "content": f"feedback: {message['content']}"}
        return dict(message)

    async def close(self) -> None:
        if self._owns_client:
            await self.client.aclose()
