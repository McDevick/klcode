import json

from kl_server.models.action import ToolResult
from kl_server.models.feedback import Feedback, FeedbackCategory


def classify_command_result(exit_code: int | None, stdout: str, stderr: str) -> Feedback:
    raw = f"{stdout}\n{stderr}"
    combined = raw.lower()
    if exit_code is None:
        return Feedback(category=FeedbackCategory.TIMEOUT, summary=(stderr or stdout) or "timeout")
    if exit_code == 0:
        return Feedback(category=FeedbackCategory.SUCCESS, summary=stdout)
    if "failed" in combined or "assert" in combined:
        return Feedback(category=FeedbackCategory.TEST_FAILURE, summary=raw[-1000:])
    return Feedback(category=FeedbackCategory.UNKNOWN, summary=raw[-1000:])


def classify_tool_result(result: ToolResult) -> Feedback:
    """Classify a ToolResult into Feedback. Structured command output wins; otherwise fall back to ok/error."""
    if result.ok is False:
        if result.error == "timeout":
            return Feedback(category=FeedbackCategory.TIMEOUT, summary="timeout")
        summary = result.error or result.output or "tool failed with no error message"
        return Feedback(category=FeedbackCategory.TOOL_ERROR, summary=summary[-1000:])
    try:
        payload = json.loads(result.output)
    except json.JSONDecodeError:
        return Feedback(category=FeedbackCategory.UNKNOWN, summary=result.output[-1000:])
    if not isinstance(payload, dict) or "exit_code" not in payload or not isinstance(payload["exit_code"], int):
        return Feedback(category=FeedbackCategory.UNKNOWN, summary=result.output[-1000:])
    return classify_command_result(
        payload["exit_code"],
        str(payload.get("stdout", "")),
        str(payload.get("stderr", "")),
    )
