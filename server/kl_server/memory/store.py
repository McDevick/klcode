import asyncio
import json
from pathlib import Path

import aiosqlite


class MemoryStore:
    def __init__(self, path: Path):
        self.path = path
        self.conn: aiosqlite.Connection | None = None
        self._connect_lock = asyncio.Lock()

    async def connect(self) -> aiosqlite.Connection:
        async with self._connect_lock:
            if self.conn is None:
                self.conn = await aiosqlite.connect(self.path)
                self.conn.row_factory = aiosqlite.Row
                await self.conn.execute(
                    "CREATE TABLE IF NOT EXISTS memory ("
                    "id INTEGER PRIMARY KEY, scope TEXT, kind TEXT, tags TEXT, content TEXT)"
                )
                await self.conn.execute(
                    "CREATE TABLE IF NOT EXISTS state ("
                    "scope TEXT, kind TEXT, content TEXT, "
                    "PRIMARY KEY (scope, kind))"
                )
                await self.conn.commit()
        return self.conn

    async def __aenter__(self) -> "MemoryStore":
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.close()

    async def _connection(self) -> aiosqlite.Connection:
        if self.conn is None:
            await self.connect()
        return self.conn

    async def add(self, scope: str, kind: str, tags: list[str], content: str) -> None:
        conn = await self._connection()
        await conn.execute(
            "INSERT INTO memory (scope, kind, tags, content) VALUES (?, ?, ?, ?)",
            (scope, kind, json.dumps(tags), content),
        )
        await conn.commit()

    async def find(self, tags: list[str]) -> list[str]:
        conn = await self._connection()
        cursor = await conn.execute("SELECT content, tags FROM memory")
        rows = await cursor.fetchall()
        return [
            row["content"]
            for row in rows
            if any(tag in json.loads(row["tags"]) for tag in tags)
        ]

    async def list_by_kind(self, scope: str, kind: str) -> list[dict]:
        conn = await self._connection()
        cursor = await conn.execute(
            "SELECT id, content, tags FROM memory "
            "WHERE scope = ? AND kind = ? ORDER BY id ASC",
            (scope, kind),
        )
        rows = await cursor.fetchall()
        return [
            {
                "id": row["id"],
                "content": row["content"],
                "tags": json.loads(row["tags"]),
            }
            for row in rows
        ]

    async def get_state(self, scope: str, kind: str) -> str | None:
        conn = await self._connection()
        cursor = await conn.execute(
            "SELECT content FROM state WHERE scope = ? AND kind = ?",
            (scope, kind),
        )
        row = await cursor.fetchone()
        return row["content"] if row is not None else None

    async def set_state(self, scope: str, kind: str, content: str) -> None:
        conn = await self._connection()
        await conn.execute(
            """
            INSERT INTO state (scope, kind, content) VALUES (?, ?, ?)
            ON CONFLICT(scope, kind) DO UPDATE SET content = excluded.content
            """,
            (scope, kind, content),
        )
        await conn.commit()

    async def delete_state(self, scope: str, kind: str) -> None:
        conn = await self._connection()
        await conn.execute(
            "DELETE FROM state WHERE scope = ? AND kind = ?",
            (scope, kind),
        )
        await conn.commit()

    async def close(self) -> None:
        async with self._connect_lock:
            if self.conn is not None:
                await self.conn.close()
                self.conn = None
