import json

from kl_server.providers.base import ProviderRequest, ProviderResponse, ProviderToolCall


class MockProvider:
    def __init__(self, responses: list[str] | None = None):
        # 每条 response：可含 JSON 动作（"前缀 {"tool":...,"args":...}"，向后兼容
        # 文本协议时期的测试写法）或最终回答文本（如 "DONE" / "DONE: xxx"）。
        self.responses = list(responses or [])
        self.calls: list[ProviderRequest] = []
        self._seq = 0

    async def complete(self, request: ProviderRequest) -> ProviderResponse:
        self.calls.append(request)
        if not self.responses:
            return ProviderResponse(text="DONE")
        text = self.responses.pop(0)
        prefix, tool_calls = self._parse_action(text)
        if tool_calls:
            return ProviderResponse(text=prefix, tool_calls=tool_calls)
        return ProviderResponse(text=text)

    def _parse_action(self, text: str) -> tuple[str, list[ProviderToolCall] | None]:
        """把兼容写法的动作文本（含 {"tool": ...} JSON）转成原生 tool_calls。

        前缀消息里可能含有花括号（如"先检查 {project} 目录"），因此从末尾
        回扫 "{" 起点，取第一个能完整解析为 JSON 的片段；无动作 JSON 时
        整体作为最终回答文本。
        """
        close = text.rfind("}")
        start = text.rfind("{", 0, close) if close >= 0 else -1
        while start >= 0:
            candidate = text[start : close + 1]
            try:
                payload = json.loads(candidate)
            except json.JSONDecodeError:
                start = text.rfind("{", 0, start)
                continue
            if not isinstance(payload, dict) or not isinstance(payload.get("tool"), str):
                return text, None
            args = payload.get("args")
            if not isinstance(args, dict):
                args = {}
            self._seq += 1
            tool_call = ProviderToolCall(
                id=f"call_{self._seq}",
                name=payload["tool"],
                arguments=json.dumps(args),
            )
            prefix = text[:start].strip()
            return prefix, [tool_call]
        return text, None
