import pytest

from kl_server.core.session_manager import SessionManager
from kl_server.core.task_manager import TaskManager
from kl_server.models.task import Session, Task, TaskStatus
from kl_server.storage.database import Database


@pytest.mark.asyncio
async def test_task_manager_pause_resume_abort_transitions(tmp_path):
    db = Database(tmp_path / "kl.db")
    try:
        sessions = SessionManager(db)
        tasks = TaskManager(db)
        await sessions.create(Session(id="s1", workspace=str(tmp_path)))
        await tasks.create(
            Task(id="t1", session_id="s1", description="x", status=TaskStatus.RUNNING)
        )
        await tasks.create(
            Task(id="t2", session_id="s1", description="y", status=TaskStatus.AWAITING_APPROVAL)
        )

        await tasks.pause("t1")
        assert (await tasks.get("t1")).status == TaskStatus.PAUSED
        with pytest.raises(ValueError):
            await tasks.pause("t1")

        await tasks.resume("t1")
        assert (await tasks.get("t1")).status == TaskStatus.RUNNING
        with pytest.raises(ValueError):
            await tasks.resume("t1")

        await tasks.pause("t2")
        assert (await tasks.get("t2")).status == TaskStatus.PAUSED

        await tasks.abort("t1")
        assert (await tasks.get("t1")).status == TaskStatus.CANCELED
        with pytest.raises(ValueError):
            await tasks.pause("t1")
    finally:
        await db.close()


@pytest.mark.asyncio
@pytest.mark.asyncio
async def test_task_manager_recovers_stale_tasks(tmp_path):
    db = Database(tmp_path / "kl.db")
    try:
        sessions = SessionManager(db)
        tasks = TaskManager(db)
        await sessions.create(Session(id="s1", workspace=str(tmp_path)))
        for task_id, status in (
            ("running", TaskStatus.RUNNING),
            ("awaiting", TaskStatus.AWAITING_APPROVAL),
            ("paused", TaskStatus.PAUSED),
            ("pending", TaskStatus.PENDING),
            ("done", TaskStatus.SUCCEEDED),
            ("canceled", TaskStatus.CANCELED),
        ):
            await tasks.create(
                Task(id=task_id, session_id="s1", description=task_id, status=status)
            )

        recovered = await tasks.recover_stale_tasks()

        assert recovered == 3
        assert (await tasks.get("running")).status == TaskStatus.FAILED
        assert (await tasks.get("awaiting")).status == TaskStatus.FAILED
        assert (await tasks.get("paused")).status == TaskStatus.FAILED
        assert (await tasks.get("pending")).status == TaskStatus.PENDING
        assert (await tasks.get("done")).status == TaskStatus.SUCCEEDED
        assert (await tasks.get("canceled")).status == TaskStatus.CANCELED
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_task_manager_pause_resume_abort_missing_raises_key_error(tmp_path):
    db = Database(tmp_path / "kl.db")
    try:
        tasks = TaskManager(db)
        with pytest.raises(KeyError):
            await tasks.pause("missing")
        with pytest.raises(KeyError):
            await tasks.resume("missing")
        with pytest.raises(KeyError):
            await tasks.abort("missing")
    finally:
        await db.close()
