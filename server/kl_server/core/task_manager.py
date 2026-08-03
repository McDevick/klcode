from kl_server.models.task import Session, Task, TaskStatus
from kl_server.storage.database import Database


class TaskManager:
    def __init__(self, db: Database):
        self.db = db

    async def create(self, task: Task) -> Task:
        self.db.conn.execute(
            "INSERT INTO tasks VALUES (?, ?, ?, ?)",
            (task.id, task.session_id, task.description, task.status.value),
        )
        self.db.conn.commit()
        return task

    async def get(self, task_id: str) -> Task:
        row = self.db.conn.execute("SELECT id, session_id, description, status FROM tasks WHERE id = ?", (task_id,)).fetchone()
        if row is None:
            raise KeyError(task_id)
        return Task(id=row[0], session_id=row[1], description=row[2], status=TaskStatus(row[3]))

    async def update(self, task: Task) -> None:
        self.db.conn.execute("UPDATE tasks SET status = ? WHERE id = ?", (task.status.value, task.id))
        self.db.conn.commit()
