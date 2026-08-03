import sqlite3
from datetime import datetime, timezone

import pytest
from kl_server.core.session_manager import SessionManager
from kl_server.core.task_manager import TaskManager
from kl_server.models.task import Session, Task, TaskStatus
from kl_server.storage.database import Database


@pytest.mark.asyncio
async def test_session_and_task_persist(tmp_path):
    db = Database(tmp_path / "kl.db")
    sessions = SessionManager(db)
    tasks = TaskManager(db)
    try:
        session = await sessions.create(Session(id="s1", workspace=str(tmp_path), name="main"))
        task = await tasks.create(Task(id="t1", session_id=session.id, description="fix"))
        loaded = await sessions.get("s1")
        task.status = TaskStatus.SUCCEEDED
        await tasks.update(task)
        assert loaded.id == "s1"
        assert (await tasks.get("t1")).status == TaskStatus.SUCCEEDED
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_full_field_roundtrip_after_reopen(tmp_path):
    path = tmp_path / "kl.db"
    created_at = datetime(2026, 8, 3, 12, 30, 0, tzinfo=timezone.utc)

    db = Database(path)
    try:
        sessions = SessionManager(db)
        tasks = TaskManager(db)
        session = Session(
            id="s-full",
            workspace="C:\\work",
            name="full",
            provider="openai",
            model="gpt-test",
            status="paused",
            created_at=created_at,
        )
        task = Task(
            id="t-full",
            session_id=session.id,
            description="full task",
            status=TaskStatus.RUNNING,
            workspace_mode="manual",
            branch="feature/storage",
            snapshot_path="snapshots/example.db",
            summary="completed",
            created_at=created_at,
        )
        await sessions.create(session)
        await tasks.create(task)
    finally:
        await db.close()

    reopened = Database(path)
    try:
        assert await SessionManager(reopened).get("s-full") == session
        assert await TaskManager(reopened).get("t-full") == task
    finally:
        await reopened.close()


@pytest.mark.asyncio
async def test_get_missing_ids_raise_key_error(tmp_path):
    db = Database(tmp_path / "kl.db")
    sessions = SessionManager(db)
    tasks = TaskManager(db)
    try:
        with pytest.raises(KeyError):
            await sessions.get("missing-session")
        with pytest.raises(KeyError):
            await tasks.get("missing-task")
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_duplicate_ids_raise_integrity_error(tmp_path):
    db = Database(tmp_path / "kl.db")
    sessions = SessionManager(db)
    tasks = TaskManager(db)
    try:
        session = Session(id="s1", workspace=str(tmp_path), name="main")
        task = Task(id="t1", session_id=session.id, description="fix")
        await sessions.create(session)
        await tasks.create(task)

        with pytest.raises(sqlite3.IntegrityError):
            await sessions.create(session)
        with pytest.raises(sqlite3.IntegrityError):
            await tasks.create(task)
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_update_missing_task_raises_key_error(tmp_path):
    db = Database(tmp_path / "kl.db")
    sessions = SessionManager(db)
    tasks = TaskManager(db)
    try:
        session = Session(id="s1", workspace=str(tmp_path), name="main")
        await sessions.create(session)
        missing = Task(id="missing-task", session_id=session.id, description="fix")
        with pytest.raises(KeyError):
            await tasks.update(missing)
    finally:
        await db.close()
