from kl_server.models.action import Action, ToolResult
from kl_server.models.feedback import Feedback, FeedbackCategory
from kl_server.models.task import Session, Task, TaskStatus


def test_action_and_result_roundtrip():
    action = Action(tool="read_file", args={"path": "a.py"}, task_id="t1")
    result = ToolResult(ok=True, output="content")
    assert action.tool == "read_file"
    assert result.ok is True


def test_feedback_category():
    feedback = Feedback(category=FeedbackCategory.TEST_FAILURE, summary="1 failed")
    assert feedback.category.value == "test_failure"


def test_session_and_task_relationships():
    session = Session(id="s1", workspace="E:/repo", name="main")
    task = Task(id="t1", session_id=session.id, description="fix tests", status=TaskStatus.PENDING)
    assert task.session_id == "s1"
