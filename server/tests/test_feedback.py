from kl_server.core.feedback import classify_command_result, classify_tool_result
from kl_server.models.action import ToolResult
from kl_server.models.feedback import FeedbackCategory


def test_exit_zero_is_success():
    feedback = classify_command_result(exit_code=0, stdout="ok", stderr="")
    assert feedback.category == FeedbackCategory.SUCCESS


def test_pytest_failure_is_test_failure():
    feedback = classify_command_result(1, "1 failed", "assert 1 == 2")
    assert feedback.category == FeedbackCategory.TEST_FAILURE


def test_timeout_is_timeout():
    feedback = classify_command_result(None, "", "timeout")
    assert feedback.category == FeedbackCategory.TIMEOUT


def test_nonzero_without_failure_markers_is_unknown():
    feedback = classify_command_result(2, "build error", "")
    assert feedback.category == FeedbackCategory.UNKNOWN


def test_failure_summary_truncates_to_last_1000_chars():
    stdout = "x" * 2000
    stderr = "FINAL FAILED"
    feedback = classify_command_result(1, stdout, stderr)
    assert feedback.category == FeedbackCategory.TEST_FAILURE
    assert len(feedback.summary) == 1000
    assert feedback.summary.endswith("FINAL FAILED")


def test_uppercase_failed_keeps_raw_summary():
    feedback = classify_command_result(1, "FAILED", "")
    assert feedback.category == FeedbackCategory.TEST_FAILURE
    assert "FAILED" in feedback.summary


def test_empty_timeout_summary_is_timeout():
    feedback = classify_command_result(None, "", "")
    assert feedback.category == FeedbackCategory.TIMEOUT
    assert feedback.summary == "timeout"


def test_classify_tool_result_timeout_error_is_timeout():
    feedback = classify_tool_result(ToolResult(ok=False, output="", error="timeout"))
    assert feedback.category == FeedbackCategory.TIMEOUT


def test_classify_tool_result_malformed_json_is_unknown():
    feedback = classify_tool_result(ToolResult(ok=True, output='{"exit_code": 1, "stdout": "1 failed"'))
    assert feedback.category == FeedbackCategory.UNKNOWN


def test_classify_tool_result_non_object_json_is_unknown():
    feedback = classify_tool_result(ToolResult(ok=True, output="[]"))
    assert feedback.category == FeedbackCategory.UNKNOWN


def test_classify_tool_result_missing_exit_code_is_unknown():
    feedback = classify_tool_result(ToolResult(ok=True, output='{"status": "ok"}'))
    assert feedback.category == FeedbackCategory.UNKNOWN
