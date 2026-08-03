import pytest
from kl_server.models.task import Session, Task, TaskStatus
from kl_server.storage.database import Database
from kl_server.core.session_manager import SessionManager
from kl_server.core.task_manager import TaskManager


@pytest.mark.asyncio
async def test_session_and_task_persist(tmp_path):
    db = Database(tmp_path / "kl.db")
    sessions = SessionManager(db)
    tasks = TaskManager(db)
    session = await sessions.create(Session(id="s1", workspace=str(tmp_path), name="main"))
    task = await tasks.create(Task(id="t1", session_id=session.id, description="fix"))
    loaded = await sessions.get("s1")
    task.status = TaskStatus.SUCCEEDED
    await tasks.update(task)
    assert loaded.id == "s1"
    assert (await tasks.get("t1")).status == TaskStatus.SUCCEEDED
