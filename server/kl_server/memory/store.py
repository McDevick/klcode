import asyncio
import json
from datetime import datetime, timezone
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
                    "id INTEGER PRIMARY KEY, scope TEXT, kind TEXT, tags TEXT, "
                    "content TEXT, created_at TEXT NOT NULL DEFAULT '')"
                )
                await self.conn.execute(
                    "CREATE TABLE IF NOT EXISTS state ("
                    "scope TEXT, kind TEXT, content TEXT, "
                    "PRIMARY KEY (scope, kind))"
                )
                await self._ensure_memory_created_at()
                await self.conn.commit()
        return self.conn

    async def _ensure_memory_created_at(self) -> None:
        """为旧库补充 created_at 列；新库建表时已包含该列。"""
        cursor = await self.conn.execute("PRAGMA table_info(memory)")
        rows = await cursor.fetchall()
        if any(row["name"] == "created_at" for row in rows):
            return
        await self.conn.execute(
            "ALTER TABLE memory ADD COLUMN created_at TEXT NOT NULL DEFAULT ''"
        )

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
            "INSERT INTO memory (scope, kind, tags, content, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                scope,
                kind,
                json.dumps(tags),
                content,
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        await conn.commit()

    async def find(
        self,
        tags: list[str],
        kinds: list[str] | None = None,
        keywords: list[str] | None = None,
        limit: int | None = None,
    ) -> list[str]:
        conn = await self._connection()
        if not tags:
            return []
        clauses = [
            "("
            + " OR ".join(
                "EXISTS (SELECT 1 FROM json_each(memory.tags) "
                "WHERE json_each.value = ?)"
                for _ in tags
            )
            + ")"
        ]
        params: list[object] = list(tags)
        if kinds:
            clauses.append(
                "kind IN (" + ", ".join("?" for _ in kinds) + ")"
            )
            params.extend(kinds)
        if keywords:
            patterns = [
                "content LIKE ? ESCAPE '!'"
                for _ in keywords
            ]
            clauses.append("(" + " OR ".join(patterns) + ")")
            params.extend(
                f"%{self._escape_like(keyword)}%"
                for keyword in keywords
            )
        sql = (
            "SELECT content FROM memory WHERE "
            + " AND ".join(clauses)
            + " ORDER BY created_at DESC, id DESC"
        )
        if limit is not None:
            sql += " LIMIT ?"
            params.append(limit)
        cursor = await conn.execute(sql, params)
        rows = await cursor.fetchall()
        return [row["content"] for row in rows]

    @staticmethod
    def _escape_like(value: str) -> str:
        return (
            value.replace("!", "!!")
            .replace("%", "!%")
            .replace("_", "!_")
        )

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


    async def delete_scope(self, scope: str) -> None:
        conn = await self._connection()
        await conn.execute("DELETE FROM memory WHERE scope = ?", (scope,))
        await conn.commit()
    async def close(self) -> None:
        async with self._connect_lock:
            if self.conn is not None:
                await self.conn.close()
                self.conn = None