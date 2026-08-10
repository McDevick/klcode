"""Mock-LLM demo: feedback loop makes the agent change its next action.

Uses the native tool-calling format: the mock provider emits tool_calls,
the loop returns tool results, and a provider with no tool_calls gives the
final answer.
"""

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _demo_import import ensure_kl_server_importable  # noqa: E402
ensure_kl_server_importable()

from kl_server.core.agent_loop import AgentLoop, LoopSettings  # noqa: E402
from kl_server.core.tool_executor import ToolExecutor  # noqa: E402
from kl_server.models.action import ToolResult  # noqa: E402
from kl_server.models.task import Session  # noqa: E402
from kl_server.providers.base import ProviderResponse, ProviderToolCall  # noqa: E402
from kl_server.providers.mock import MockProvider  # noqa: E402
from kl_server.tools.base import Tool, ToolContext  # noqa: E402
from kl_server.tools.registry import ToolRegistry  # noqa: E402


class FakeRunTests(Tool):
    name = "run_tests"
    description = "Fake test runner used only by the mock-LLM demo."
    schema = {"type": "object", "properties": {"attempt": {"type": "integer"}}}

    async def execute(self, args: dict, ctx: ToolContext) -> ToolResult:
        if args.get("attempt") == 1:
            return ToolResult(
                ok=True,
                output=json.dumps(
                    {
                        "exit_code": 1,
                        "stdout": "assert failed: test_app_basic",
                        "stderr": "",
                    }
                ),
            )
        return ToolResult(
            ok=True,
            output=json.dumps(
                {"exit_code": 0, "stdout": "all tests passed", "stderr": ""}
            ),
        )


class FeedbackAwareMockProvider(MockProvider):
    """MockProvider that picks its next tool call from the last feedback."""

    def __init__(self) -> None:
        super().__init__(responses=[])
        self.timeline: list[dict] = []
        self.actions: list[dict] = []
        self._snapshots: list[list[dict]] = []
        self._seq = 0

    def _call(self, name: str, args: dict) -> ProviderResponse:
        self._seq += 1
        return ProviderResponse(
            text="下一步",
            tool_calls=[
                ProviderToolCall(
                    id=f"call_{self._seq}",
                    name=name,
                    arguments=json.dumps(args),
                )
            ],
        )

    async def complete(self, request):
        self.calls.append(request)
        snapshot = [dict(message) for message in request.messages]
        self._snapshots.append(snapshot)
        feedback = [
            str(message.get("content", ""))
            for message in snapshot
            if message.get("role") == "user"
            and str(message.get("content", "")).startswith("feedback")
        ]
        if not feedback:
            return self._call("run_tests", {"attempt": 1})
        if "test_failure" in feedback[-1]:
            return self._call("run_tests", {"attempt": 2})
        return ProviderResponse(text="DONE")


async def run_demo():
    """Drive AgentLoop with the adaptive provider and return the result."""

    provider = FeedbackAwareMockProvider()
    registry = ToolRegistry()
    registry.register(FakeRunTests())
    loop = AgentLoop(
        provider=provider,
        tools=ToolExecutor(registry),
        settings=LoopSettings(max_iterations=5),
    )
    result = await loop.run(
        Session(id="demo-feedback", workspace=".", name="feedback-demo"),
        "Run the tests, fix failures, and stop only when they pass.",
    )

    final = provider._snapshots[-1]
    for message in final:
        if message["role"] == "user" and str(message["content"]).startswith("feedback"):
            for line in str(message["content"]).splitlines()[1:]:
                category, _, summary = line.partition(": ")
                provider.timeline.append(
                    {"category": category, "summary": summary.strip()}
                )
        elif message["role"] == "assistant":
            for call in message.get("tool_calls") or []:
                try:
                    arguments = json.loads(call["function"]["arguments"])
                    provider.actions.append(
                        {"name": call["function"]["name"], "args": arguments}
                    )
                except (json.JSONDecodeError, KeyError):
                    pass
    return provider, result


def main() -> None:
    provider, result = asyncio.run(run_demo())
    print(f"feedback: agent loop finished with {result!r}")
    print("feedback timeline:")
    for entry in provider.timeline:
        print(f"  {entry['category']} -> {entry['summary']}")
    attempts = [entry["args"]["attempt"] for entry in provider.actions]
    print(f"feedback: next action changed across attempts {attempts}")
    assert result == "DONE"
    assert [entry["category"] for entry in provider.timeline] == [
        "test_failure",
        "success",
    ]


if __name__ == "__main__":
    main()
