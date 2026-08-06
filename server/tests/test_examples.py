"""Tests for the Phase 5.1 mock-LLM mechanism demos.

Each demo is a runnable script with a testable entry point. These tests drive
the same functions the scripts run so the examples stay in sync with the
underlying kl_server mechanisms.
"""

import sys
from pathlib import Path

from kl_server.core.context import AssembledContext
from kl_server.core.feedback import FeedbackCategory
from kl_server.models.action import ToolResult


REPO_ROOT = Path(__file__).resolve().parents[2]
EXAMPLES_DIR = REPO_ROOT / "examples"
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import examples.context_demo as context_demo  # noqa: E402
import examples.feedback_demo as feedback_demo  # noqa: E402
import examples.guardrail_demo as guardrail_demo  # noqa: E402
import examples.tool_error_demo as tool_error_demo  # noqa: E402


def test_guardrail_demo_classifies_destructive_command():
    assert guardrail_demo.classify_command("rm -rf /") == "critical"


async def test_feedback_demo_loop_adapts_and_reports_timeline():
    provider, result = await feedback_demo.run_demo()

    assert result == "DONE"
    categories = [
        message["category"]
        for message in provider.timeline
    ]
    assert categories == [
        FeedbackCategory.TEST_FAILURE.value,
        FeedbackCategory.SUCCESS.value,
    ]
    attempts = [action["attempt"] for action in provider.actions]
    assert attempts == [1, 2]
    assert provider.timeline[0]["summary"].startswith("assert")
    assert provider.timeline[1]["summary"].startswith("all")


async def test_context_demo_builds_within_budget_and_summarizes():
    provider, result = await context_demo.run_demo()

    assert isinstance(result, AssembledContext)
    assert result.used_tokens <= context_demo.TOKEN_BUDGET
    assert result.contains_priority(context_demo.SUMMARY_MARKER)
    assert len(provider.calls) == 1


async def test_tool_error_demo_reports_caught_error():
    result = await tool_error_demo.run_demo()

    assert isinstance(result, ToolResult)
    assert result.ok is False
    assert result.error == "boom"
