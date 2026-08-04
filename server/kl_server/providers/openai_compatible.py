import httpx

from kl_server.providers.base import ProviderRequest, ProviderResponse


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

    async def complete(self, request: ProviderRequest) -> ProviderResponse:
        model = request.model or self.model
        headers = {}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        messages = [
            self._normalize_message(message)
            for message in request.messages
        ]
        try:
            response = await self.client.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json={
                    "model": model,
                    "messages": messages,
                    "max_tokens": request.max_tokens,
                },
            )
            response.raise_for_status()
        except httpx.TimeoutException as exc:
            raise ProviderError("provider timeout") from exc
        except httpx.HTTPStatusError as exc:
            raise ProviderError(f"provider http error: {exc.response.status_code}") from exc

        try:
            data = response.json()
        except ValueError as exc:
            raise ProviderError("unexpected provider response") from exc
        if not isinstance(data, dict):
            raise ProviderError("unexpected provider response")
        choices = data.get("choices")
        if not isinstance(choices, list) or not choices:
            raise ProviderError("unexpected provider response")
        first_choice = choices[0]
        if not isinstance(first_choice, dict):
            raise ProviderError("unexpected provider response")
        message = first_choice.get("message")
        if not isinstance(message, dict):
            raise ProviderError("unexpected provider response")
        content = message.get("content")
        if not isinstance(content, str):
            raise ProviderError("unexpected provider response")
        return ProviderResponse(text=content, raw=data)

    def _normalize_message(self, message: dict[str, str]) -> dict[str, str]:
        role = message.get("role")
        if role == "feedback":
            return {"role": "user", "content": f"feedback: {message['content']}"}
        if role == "tool":
            return {"role": "user", "content": f"tool_result: {message['content']}"}
        return dict(message)

    async def close(self) -> None:
        if self._owns_client:
            await self.client.aclose()
