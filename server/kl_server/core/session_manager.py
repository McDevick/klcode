from datetime import datetime

from kl_server.models.task import Session
from kl_server.storage.database import Database


class SessionManager:
    def __init__(self, db: Database):
        self.db = db

    async def create(self, session: Session) -> Session:
        conn = await self.db.connect()
        await conn.execute(
            """
            INSERT INTO sessions (id, workspace, name, provider, model, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                session.id,
                session.workspace,
                session.name,
                session.provider,
                session.model,
                session.status,
                session.created_at.isoformat(),
            ),
        )
        await conn.commit()
        return session

    async def get(self, session_id: str) -> Session:
        conn = await self.db.connect()
        cursor = await conn.execute(
            """
            SELECT id, workspace, name, provider, model, status, created_at
            FROM sessions
            WHERE id = ?
            """,
            (session_id,),
        )
        row = await cursor.fetchone()
        if row is None:
            raise KeyError(session_id)
        return self._row_to_session(row)

    async def list(self) -> list[Session]:
        conn = await self.db.connect()
        cursor = await conn.execute(
            """
            SELECT id, workspace, name, provider, model, status, created_at
            FROM sessions
            ORDER BY created_at
            """
        )
        rows = await cursor.fetchall()
        return [self._row_to_session(row) for row in rows]

    async def update(self, session: Session) -> None:
        conn = await self.db.connect()
        cursor = await conn.execute(
            """
            UPDATE sessions
            SET workspace = ?, name = ?, provider = ?, model = ?, status = ?
            WHERE id = ?
            """,
            (
                session.workspace,
                session.name,
                session.provider,
                session.model,
                session.status,
                session.id,
            ),
        )
        if cursor.rowcount == 0:
            raise KeyError(session.id)
        await conn.commit()

    async def delete(self, session_id: str) -> None:
        conn = await self.db.connect()
        cursor = await conn.execute(
            "DELETE FROM sessions WHERE id = ?",
            (session_id,),
        )
        await conn.commit()
        if cursor.rowcount == 0:
            raise KeyError(session_id)

    @staticmethod
    def _row_to_session(row) -> Session:
        return Session(
            id=row["id"],
            workspace=row["workspace"],
            name=row["name"],
            provider=row["provider"],
            model=row["model"],
            status=row["status"],
            created_at=datetime.fromisoformat(row["created_at"]),
        )
