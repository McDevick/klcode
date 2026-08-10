from dataclasses import dataclass
from enum import Enum


class FeedbackCategory(str, Enum):
    SUCCESS = "success"
    TEST_FAILURE = "test_failure"
    BUILD_FAILURE = "build_failure"
    LINT_ERROR = "lint_error"
    TYPE_ERROR = "type_error"
    TIMEOUT = "timeout"
    TOOL_ERROR = "tool_error"
    PROVIDER_ERROR = "provider_error"
    UNKNOWN = "unknown_error"


@dataclass(frozen=True)
class Feedback:
    category: FeedbackCategory
    summary: str
    raw_ref: str | None = None
