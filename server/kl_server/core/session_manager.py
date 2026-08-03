from kl_server.models.task import Session, Task, TaskStatus
from kl_server.storage.database import Database


class SessionManager:
    def __init__(self, db: Database):
        self.db = db

    async def create(self, session: Session) -> Session:
        self.db.conn.execute(
            "INSERT INTO sessions VALUES (?, ?, ?, ?, ?, ?)",
            (session.id, session.workspace, session.name, session.provider, session.model, session.status),
        )
        self.db.conn.commit()
        return session

    async def get(self, session_id: str) -> Session:
        row = self.db.conn.execute(
            "SELECT id, workspace, name, provider, model, status FROM sessions WHERE id = ?", (session_id,)
        ).fetchone()
        if row is None:
            raise KeyError(session_id)
        return Session(id=row[0], workspace=row[1], name=row[2], provider=row[3], model=row[4], status=row[5])
