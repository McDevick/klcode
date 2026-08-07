import json
import math
import re

from kl_server.core.tool_categories import COMMAND_TOOLS
from kl_server.models.action import ToolResult
from kl_server.models.feedback import Feedback, FeedbackCategory


_SENSITIVE_PREFIX_RE = re.compile(
    r"(sk-[a-z0-9_-]+|ghp_[a-z0-9]+|AKIA[0-9a-z]{16})",
    re.I,
)
_GENERIC_SECRET_RE = re.compile(
    r"\b(api[_-]?key|secret|token|password)\s*[=:]\s*([^\s\"']+)",
    re.I,
)


def _shannon_entropy(value: str) -> float:
    if not value:
        return 0.0
    counts = {}
    for char in value:
        counts[char] = counts.get(char, 0) + 1
    length = len(value)
    return -sum((count / length) * math.log2(count / length) for count in counts.values())


def _looks_like_secret(value: str) -> bool:
    stripped = value.strip().strip("\"'")
    if len(stripped) < 8:
        return False
    if any(char.isspace() for char in stripped):
        return False
    return _shannon_entropy(stripped) >= 3.2


def _redact_feedback(text: str) -> str:
    redacted = _SENSITIVE_PREFIX_RE.sub("[REDACTED]", text)

    def replace_generic(match: re.Match[str]) -> str:
        label = match.group(1)
        value = match.group(2)
        if _looks_like_secret(value):
            return f"{label}: [REDACTED]"
        return match.group(0)

    return _GENERIC_SECRET_RE.sub(replace_generic, redacted)


def _sanitize_feedback(text: str, max_length: int = 1000) -> str:
    redacted = _redact_feedback(text or "")
    # 去除重复行，保留最后 max_length 字符，避免同一轮重复信息灌入模型。
    deduped = "\n".join(dict.fromkeys(redacted.splitlines()))
    return deduped[-max_length:]


def classify_command_result(
    exit_code: int | None,
    stdout: str,
    stderr: str,
    tool: str = "",
) -> Feedback:
    raw = f"{stdout}\n{stderr}"
    combined = raw.lower()
    tool_lower = tool.lower()
    if exit_code is None:
        summary = _sanitize_feedback((stderr or stdout) or "timeout")
        return Feedback(category=FeedbackCategory.TIMEOUT, summary=summary)
    if exit_code == 0:
        return Feedback(category=FeedbackCategory.SUCCESS, summary=_sanitize_feedback(stdout))
    if tool_lower in {"run_tests", "test"} or "pytest" in combined:
        return Feedback(
            category=FeedbackCategory.TEST_FAILURE,
            summary=_sanitize_feedback(raw),
        )
    if tool_lower in {"run_lint", "lint"} or any(
        marker in combined for marker in ("eslint", "ruff", "pylint", "lint")
    ):
        return Feedback(
            category=FeedbackCategory.LINT_ERROR,
            summary=_sanitize_feedback(raw),
        )
    if tool_lower in {"typecheck", "type-check"} or any(
        marker in combined for marker in ("typeerror", "type error", "typescript", "error ts")
    ):
        return Feedback(
            category=FeedbackCategory.TYPE_ERROR,
            summary=_sanitize_feedback(raw),
        )
    if "build" in tool_lower or any(
        marker in combined
        for marker in (
            "build failed",
            "build error",
            "fatal error",
            "cannot find",
            "undefined reference",
            "compilation",
            "linker",
        )
    ):
        return Feedback(
            category=FeedbackCategory.BUILD_FAILURE,
            summary=_sanitize_feedback(raw),
        )
    return Feedback(category=FeedbackCategory.UNKNOWN, summary=_sanitize_feedback(raw))


def classify_tool_result(result: ToolResult, tool: str = "") -> Feedback:
    """Classify a ToolResult into Feedback. Structured command output wins; otherwise fall back to ok/error."""
    if result.ok is False:
        if result.error == "timeout":
            return Feedback(category=FeedbackCategory.TIMEOUT, summary="timeout")
        summary = result.error or result.output or "tool failed with no error message"
        return Feedback(category=FeedbackCategory.TOOL_ERROR, summary=_sanitize_feedback(summary))
    if tool not in COMMAND_TOOLS:
        return Feedback(category=FeedbackCategory.SUCCESS, summary=_sanitize_feedback(result.output))
    try:
        payload = json.loads(result.output)
    except json.JSONDecodeError:
        return Feedback(category=FeedbackCategory.UNKNOWN, summary=_sanitize_feedback(result.output))
    if not isinstance(payload, dict) or "exit_code" not in payload or not isinstance(payload["exit_code"], int):
        return Feedback(category=FeedbackCategory.UNKNOWN, summary=_sanitize_feedback(result.output))
    return classify_command_result(
        payload["exit_code"],
        str(payload.get("stdout", "")),
        str(payload.get("stderr", "")),
        tool,
    )
