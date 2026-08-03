from kl_server.models.feedback import Feedback, FeedbackCategory


def classify_command_result(exit_code: int | None, stdout: str, stderr: str) -> Feedback:
    combined = f"{stdout}\n{stderr}".lower()
    if exit_code is None:
        return Feedback(category=FeedbackCategory.TIMEOUT, summary=stderr or stdout)
    if exit_code == 0:
        return Feedback(category=FeedbackCategory.SUCCESS, summary=stdout)
    if "failed" in combined or "assert" in combined:
        return Feedback(category=FeedbackCategory.TEST_FAILURE, summary=combined[-1000:])
    return Feedback(category=FeedbackCategory.UNKNOWN, summary=combined[-1000:])
