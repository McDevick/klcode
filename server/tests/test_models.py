from dataclasses import FrozenInstanceError

import pytest

from kl_server.models.action import Action, ToolResult
from kl_server.models.feedback import Feedback, FeedbackCategory
from kl_server.models.task import Session, Task, TaskStatus


def test_action_and_result_roundtrip():
    action = Action(tool="read_file", args={"path": "a.py"}, task_id="t1")
    result = ToolResult(ok=True, output="content")
    assert action.tool == "read_file"
    assert result.ok is True


def test_action_defaults():
    action = Action(tool="read_file", args={"path": "a.py"}, task_id="t1")
    assert action.seq == 0
    assert action.workspace == ""
    assert action.raw_command is None


def test_action_is_frozen():
    action = Action(tool="read_file", args={"path": "a.py"}, task_id="t1")
    with pytest.raises(FrozenInstanceError):
        action.seq = 1


def test_tool_result_error_defaults_to_none():
    result = ToolResult(ok=True, output="content")
    assert result.error is None


def test_feedback_category():
    feedback = Feedback(category=FeedbackCategory.TEST_FAILURE, summary="1 failed")
    assert feedback.category.value == "test_failure"


def test_feedback_raw_ref_defaults_to_none():
    feedback = Feedback(category=FeedbackCategory.SUCCESS, summary="ok")
    assert feedback.raw_ref is None


def test_feedback_category_values():
    expected = {
        "SUCCESS": "success",
        "TEST_FAILURE": "test_failure",
        "BUILD_FAILURE": "build_failure",
        "LINT_ERROR": "lint_error",
        "TYPE_ERROR": "type_error",
        "TIMEOUT": "timeout",
        "TOOL_ERROR": "tool_error",
        "PROVIDER_ERROR": "provider_error",
        "UNKNOWN": "unknown_error",
    }
    assert {member.name: member.value for member in FeedbackCategory} == expected


def test_task_status_values():
    expected = {
        "PENDING": "pending",
        "RUNNING": "running",
        "AWAITING_APPROVAL": "awaiting_approval",
        "PAUSED": "paused",
        "SUCCEEDED": "succeeded",
        "FAILED": "failed",
        "CANCELED": "canceled",
    }
    assert {member.name: member.value for member in TaskStatus} == expected


def test_session_and_task_relationships():
    session = Session(id="s1", workspace="E:/repo", name="main")
    task = Task(id="t1", session_id=session.id, description="fix tests", status=TaskStatus.PENDING)
    assert task.session_id == "s1"


def test_session_and_task_defaults():
    session = Session(id="s1", workspace="E:/repo")
    task = Task(id="t1", session_id="s1", description="fix tests")
    assert task.status is TaskStatus.PENDING
    assert session.created_at.tzinfo is not None
    assert task.created_at.tzinfo is not None
