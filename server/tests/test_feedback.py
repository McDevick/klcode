from kl_server.core.feedback import classify_command_result, classify_tool_result
from kl_server.models.action import ToolResult
from kl_server.models.feedback import FeedbackCategory


def test_exit_zero_is_success():
    feedback = classify_command_result(exit_code=0, stdout="ok", stderr="")
    assert feedback.category == FeedbackCategory.SUCCESS


def test_pytest_failure_is_test_failure():
    feedback = classify_command_result(1, "1 failed", "assert 1 == 2", tool="run_tests")
    assert feedback.category == FeedbackCategory.TEST_FAILURE


def test_timeout_is_timeout():
    feedback = classify_command_result(None, "", "timeout")
    assert feedback.category == FeedbackCategory.TIMEOUT


def test_build_error_is_build_failure():
    feedback = classify_command_result(2, "build error", "")
    assert feedback.category == FeedbackCategory.BUILD_FAILURE


def test_failure_summary_truncates_to_last_1000_chars():
    stdout = "x" * 2000
    stderr = "FINAL FAILED"
    feedback = classify_command_result(1, stdout, stderr, tool="run_tests")
    assert feedback.category == FeedbackCategory.TEST_FAILURE
    assert len(feedback.summary) == 1000
    assert feedback.summary.endswith("FINAL FAILED")


def test_uppercase_failed_keeps_raw_summary():
    feedback = classify_command_result(1, "FAILED", "", tool="run_tests")
    assert feedback.category == FeedbackCategory.TEST_FAILURE
    assert "FAILED" in feedback.summary


def test_empty_timeout_summary_is_timeout():
    feedback = classify_command_result(None, "", "")
    assert feedback.category == FeedbackCategory.TIMEOUT
    assert feedback.summary == "timeout"


def test_classify_tool_result_timeout_error_is_timeout():
    feedback = classify_tool_result(ToolResult(ok=False, output="", error="timeout"))
    assert feedback.category == FeedbackCategory.TIMEOUT


def test_classify_tool_result_uses_output_when_error_is_missing():
    feedback = classify_tool_result(
        ToolResult(ok=False, output="ERROR: boom", error=None),
        tool="mcp_demo_shell",
    )
    assert feedback.category == FeedbackCategory.TOOL_ERROR
    assert "ERROR: boom" in feedback.summary


def test_classify_tool_result_malformed_json_is_unknown():
    feedback = classify_tool_result(
        ToolResult(ok=True, output='{"exit_code": 1, "stdout": "1 failed"'),
        tool="run_command",
    )
    assert feedback.category == FeedbackCategory.UNKNOWN


def test_classify_tool_result_non_object_json_is_unknown():
    feedback = classify_tool_result(ToolResult(ok=True, output="[]"), tool="run_command")
    assert feedback.category == FeedbackCategory.UNKNOWN


def test_classify_tool_result_missing_exit_code_is_unknown():
    feedback = classify_tool_result(ToolResult(ok=True, output='{"status": "ok"}'), tool="run_command")
    assert feedback.category == FeedbackCategory.UNKNOWN


def test_classify_tool_result_plain_output_is_success():
    feedback = classify_tool_result(ToolResult(ok=True, output="hello"))
    assert feedback.category == FeedbackCategory.SUCCESS


def test_lint_error_is_lint_failure():
    feedback = classify_tool_result(
        ToolResult(
            ok=True,
            output='{"exit_code": 1, "stdout": "eslint: unexpected console", "stderr": ""}',
        ),
        tool="run_lint",
    )
    assert feedback.category == FeedbackCategory.LINT_ERROR


def test_type_error_is_type_failure():
    feedback = classify_tool_result(
        ToolResult(
            ok=True,
            output='{"exit_code": 1, "stdout": "error TS2322: type mismatch", "stderr": ""}',
        ),
        tool="typecheck",
    )
    assert feedback.category == FeedbackCategory.TYPE_ERROR


def test_command_build_failure_is_build_failure():
    feedback = classify_command_result(1, "Build failed", "")
    assert feedback.category == FeedbackCategory.BUILD_FAILURE


def test_generic_command_assertion_is_unknown_not_test_failure():
    feedback = classify_command_result(1, "AssertionError: value invalid", "")
    assert feedback.category == FeedbackCategory.UNKNOWN


def test_feedback_redacts_secrets_and_dedupes_lines():
    summary = "api_key=sk-super-secret\napi_key=sk-super-secret\nbuild failed"
    feedback = classify_command_result(1, summary, "")
    assert "sk-super-secret" not in feedback.summary
    assert feedback.summary.count("[REDACTED]") == 1
    assert feedback.summary.endswith("build failed")


def test_generic_token_does_not_redact_code_like_token():
    feedback = classify_command_result(1, "token: SomeClass", "")
    assert "SomeClass" in feedback.summary
