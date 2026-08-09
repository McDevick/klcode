import asyncio
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import aiosqlite
import pytest
from kl_server.core.session_manager import SessionManager
from kl_server.core.task_manager import TaskManager
from kl_server.models.task import Session, Task, TaskStatus
from kl_server.storage.database import Database, DatabaseCorruptionError


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
async def test_concurrent_connect_opens_single_connection(tmp_path):
    db = Database(tmp_path / "kl.db")
    try:
        with patch("aiosqlite.connect", wraps=aiosqlite.connect) as connect:
            await asyncio.gather(db.connect(), db.connect())
            connect.assert_called_once()
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_corrupt_database_is_backed_up_and_blocks_writes(tmp_path):
    path = tmp_path / "kl.db"
    path.write_text("not a sqlite database", encoding="utf-8")
    db = Database(path)
    sessions = SessionManager(db)

    with pytest.raises(DatabaseCorruptionError) as exc_info:
        await db.connect()

    message = str(exc_info.value)
    assert "backup:" in message
    assert "writes blocked" in message
    assert db.corrupt_backup is not None
    assert Path(db.corrupt_backup).exists()

    with pytest.raises(DatabaseCorruptionError):
        await db.connect()
    with pytest.raises(DatabaseCorruptionError):
        await sessions.create(Session(id="s1", workspace=str(tmp_path)))


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
async def test_database_next_sequence_is_unique_concurrently(tmp_path):
    db = Database(tmp_path / "kl.db")
    try:
        values = await asyncio.gather(
            *(db.next_sequence("session") for _ in range(20))
        )
        assert values == list(range(1, 21))
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_database_sequence_seeds_from_existing_ids(tmp_path):
    path = tmp_path / "kl.db"
    conn = await aiosqlite.connect(path)
    await conn.executescript(
        """
        CREATE TABLE sessions (
            id TEXT PRIMARY KEY, workspace TEXT NOT NULL, name TEXT NOT NULL,
            provider TEXT NOT NULL, model TEXT NOT NULL, status TEXT NOT NULL,
            rules TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL
        );
        CREATE TABLE tasks (
            id TEXT PRIMARY KEY, session_id TEXT NOT NULL REFERENCES sessions(id),
            description TEXT NOT NULL, status TEXT NOT NULL, workspace_mode TEXT NOT NULL,
            branch TEXT, snapshot_path TEXT, summary TEXT NOT NULL, created_at TEXT NOT NULL
        );
        """
    )
    await conn.execute(
        "INSERT INTO sessions (id, workspace, name, provider, model, status, rules, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        ("s5", str(tmp_path), "s5", "mock", "mock-model", "active", "", "2026-08-09T00:00:00+00:00"),
    )
    await conn.execute(
        "INSERT INTO tasks (id, session_id, description, status, workspace_mode, branch, snapshot_path, summary, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ("t3", "s5", "fix", "pending", "managed", None, None, "", "2026-08-09T00:00:00+00:00"),
    )
    await conn.commit()
    await conn.close()

    db = Database(path)
    try:
        await db.connect()
        assert await db.next_sequence("session") == 6
        assert await db.next_sequence("task") == 4
    finally:
        await db.close()


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


@pytest.mark.asyncio
async def test_task_requires_existing_session(tmp_path):
    db = Database(tmp_path / "kl.db")
    tasks = TaskManager(db)
    try:
        with pytest.raises(sqlite3.IntegrityError):
            await tasks.create(Task(id="orphan", session_id="missing", description="x"))
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_session_manager_list_update_delete(tmp_path):
    db = Database(tmp_path / "kl.db")
    sessions = SessionManager(db)
    try:
        first = Session(id="s1", workspace=str(tmp_path), name="first")
        second = Session(id="s2", workspace=str(tmp_path), name="second")
        await sessions.create(first)
        await sessions.create(second)

        assert sorted(session.id for session in await sessions.list()) == ["s1", "s2"]

        first.name = "renamed"
        await sessions.update(first)
        assert (await sessions.get("s1")).name == "renamed"

        await sessions.delete("s1")
        assert [session.id for session in await sessions.list()] == ["s2"]
        with pytest.raises(KeyError):
            await sessions.delete("s1")
    finally:
        await db.close()
