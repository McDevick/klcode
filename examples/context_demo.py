"""Mock-LLM demo: assemble context under a token budget and summarize."""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _demo_import import ensure_kl_server_importable  # noqa: E402
ensure_kl_server_importable()

from kl_server.core.context import ContextAssembler, LLMSummarizer  # noqa: E402
from kl_server.providers.mock import MockProvider  # noqa: E402


TOKEN_BUDGET = 90
SUMMARY_MARKER = "Prefix-summary:"


async def run_demo():
    """Build a token-budgeted context that summarizes overflowing history."""

    provider = MockProvider(responses=[f"{SUMMARY_MARKER} fixed in retry; all green"])
    assembler = ContextAssembler(max_tokens=TOKEN_BUDGET, token_estimator=len)
    assembler.summarizer = LLMSummarizer(provider, model="mock-model")
    history = [
        'assistant: {"tool": "run_tests", "args": {"target": "app_tests"}}',
        'tool: {"exit_code": 1, "stdout": "2 failed, 1 assert", "stderr": ""}',
        "feedback: test_failure: 2 failed, 1 assert",
        'assistant: {"tool": "run_tests", "args": {"target": "app_tests", "retry": true}}',
        "feedback: success: all tests passed",
        "user: final status?",
    ]
    result = await assembler.build(
        tool_catalog=[],
        rules="rules",
        memory=[],
        history=history,
        task_id="demo-context",
    )
    return provider, result


def main() -> None:
    provider, result = asyncio.run(run_demo())
    print(f"context: budget={TOKEN_BUDGET} used={result.used_tokens}")
    print("context: summarizer output =", repr(result.text))
    assert result.used_tokens <= TOKEN_BUDGET
    assert SUMMARY_MARKER in result.text


if __name__ == "__main__":
    main()
