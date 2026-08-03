import aiosqlite
from pathlib import Path


class Database:
    def __init__(self, path: Path):
        self.path = path
        self.conn: aiosqlite.Connection | None = None

    async def connect(self) -> aiosqlite.Connection:
        if self.conn is None:
            self.conn = await aiosqlite.connect(self.path)
            self.conn.row_factory = aiosqlite.Row
            await self.conn.execute("PRAGMA foreign_keys = ON")
            await self.conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY,
                    workspace TEXT NOT NULL,
                    name TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    model TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS tasks (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL REFERENCES sessions(id),
                    description TEXT NOT NULL,
                    status TEXT NOT NULL,
                    workspace_mode TEXT NOT NULL,
                    branch TEXT,
                    snapshot_path TEXT,
                    summary TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                """
            )
            await self.conn.commit()
        return self.conn

    async def close(self) -> None:
        if self.conn is not None:
            await self.conn.close()
            self.conn = None
