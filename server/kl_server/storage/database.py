import asyncio
import shutil
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import aiosqlite


class DatabaseCorruptionError(RuntimeError):
    pass


class Database:
    def __init__(self, path: Path):
        self.path = path
        self.conn: aiosqlite.Connection | None = None
        self._connect_lock = asyncio.Lock()
        self.corrupt_backup: str | None = None

    def _backup_corrupt_database(self) -> Path:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        backup = self.path.with_name(
            f"{self.path.name}.corrupt.{timestamp}.{uuid4().hex[:8]}"
        )
        if self.path.is_file():
            try:
                shutil.copy2(self.path, backup)
            except OSError:
                pass
        return backup

    async def connect(self) -> aiosqlite.Connection:
        async with self._connect_lock:
            if self.corrupt_backup is not None:
                raise DatabaseCorruptionError(
                    f"database is corrupt; backup: {self.corrupt_backup}; writes blocked"
                )
            if self.conn is None:
                try:
                    self.conn = await aiosqlite.connect(self.path)
                    self.conn.row_factory = aiosqlite.Row
                    await self.conn.execute("PRAGMA foreign_keys = ON")
                    if self.path.is_file() and self.path.stat().st_size > 0:
                        cursor = await self.conn.execute("PRAGMA quick_check")
                        row = await cursor.fetchone()
                        if row is None or row[0] != "ok":
                            backup = self._backup_corrupt_database()
                            self.corrupt_backup = str(backup)
                            await self.conn.close()
                            self.conn = None
                            raise DatabaseCorruptionError(
                                f"database is corrupt; backup: {backup}; writes blocked"
                            )
                    await self.conn.executescript(
                        """
                        CREATE TABLE IF NOT EXISTS sessions (
                            id TEXT PRIMARY KEY,
                            workspace TEXT NOT NULL,
                            name TEXT NOT NULL,
                            provider TEXT NOT NULL,
                            model TEXT NOT NULL,
                            status TEXT NOT NULL,
                            rules TEXT NOT NULL DEFAULT '',
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
                    # 迁移：旧库无 rules 列，追加后所有读取操作才正常。
                    for stmt in [
                        "ALTER TABLE sessions ADD COLUMN rules TEXT NOT NULL DEFAULT ''",
                    ]:
                        try:
                            await self.conn.execute(stmt)
                        except Exception:
                            pass
                    await self.conn.commit()
                except DatabaseCorruptionError:
                    raise
                except Exception as exc:
                    if self.conn is not None:
                        try:
                            await self.conn.close()
                        except Exception:
                            pass
                        self.conn = None
                    backup = self._backup_corrupt_database()
                    self.corrupt_backup = str(backup)
                    raise DatabaseCorruptionError(
                        f"database is corrupt; backup: {backup}; writes blocked"
                    ) from exc
            return self.conn

    async def close(self) -> None:
        async with self._connect_lock:
            if self.conn is not None:
                await self.conn.close()
                self.conn = None
