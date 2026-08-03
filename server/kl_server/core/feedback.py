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
