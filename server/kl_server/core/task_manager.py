from datetime import datetime

from kl_server.models.task import Task, TaskStatus
from kl_server.storage.database import Database


class TaskManager:
    def __init__(self, db: Database):
        self.db = db

    async def create(self, task: Task) -> Task:
        conn = await self.db.connect()
        await conn.execute(
            """
            INSERT INTO tasks (
                id, session_id, description, status, workspace_mode,
                branch, snapshot_path, summary, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                task.id,
                task.session_id,
                task.description,
                task.status.value,
                task.workspace_mode,
                task.branch,
                task.snapshot_path,
                task.summary,
                task.created_at.isoformat(),
            ),
        )
        await conn.commit()
        return task

    async def get(self, task_id: str) -> Task:
        conn = await self.db.connect()
        cursor = await conn.execute(
            """
            SELECT id, session_id, description, status, workspace_mode,
                   branch, snapshot_path, summary, created_at
            FROM tasks
            WHERE id = ?
            """,
            (task_id,),
        )
        row = await cursor.fetchone()
        if row is None:
            raise KeyError(task_id)
        return self._row_to_task(row)

    async def list(self) -> list[Task]:
        conn = await self.db.connect()
        cursor = await conn.execute(
            """
            SELECT id, session_id, description, status, workspace_mode,
                   branch, snapshot_path, summary, created_at
            FROM tasks
            ORDER BY created_at
            """
        )
        rows = await cursor.fetchall()
        return [self._row_to_task(row) for row in rows]

    @staticmethod
    def _row_to_task(row) -> Task:
        return Task(
            id=row["id"],
            session_id=row["session_id"],
            description=row["description"],
            status=TaskStatus(row["status"]),
            workspace_mode=row["workspace_mode"],
            branch=row["branch"],
            snapshot_path=row["snapshot_path"],
            summary=row["summary"],
            created_at=datetime.fromisoformat(row["created_at"]),
        )

    async def update(self, task: Task) -> None:
        conn = await self.db.connect()
        cursor = await conn.execute(
            """
            UPDATE tasks
            SET status = ?, workspace_mode = ?, branch = ?, snapshot_path = ?, summary = ?
            WHERE id = ?
            """,
            (
                task.status.value,
                task.workspace_mode,
                task.branch,
                task.snapshot_path,
                task.summary,
                task.id,
            ),
        )
        if cursor.rowcount == 0:
            raise KeyError(task.id)
        await conn.commit()

    async def pause(self, task_id: str) -> None:
        task = await self.get(task_id)
        if task.status not in (TaskStatus.RUNNING, TaskStatus.AWAITING_APPROVAL):
            raise ValueError(f"cannot pause task in {task.status.value}")
        task.status = TaskStatus.PAUSED
        await self.update(task)

    async def resume(self, task_id: str) -> None:
        task = await self.get(task_id)
        if task.status != TaskStatus.PAUSED:
            raise ValueError(f"cannot resume task in {task.status.value}")
        task.status = TaskStatus.RUNNING
        await self.update(task)

    async def abort(self, task_id: str) -> None:
        task = await self.get(task_id)
        task.status = TaskStatus.CANCELED
        await self.update(task)
