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

    async def close(self) -> None:
        async with self._connect_lock:
            if self.conn is not None:
                await self.conn.close()
                self.conn = None
