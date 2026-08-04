import sqlite3
from pathlib import Path


class MemoryStore:
    def __init__(self, path: Path):
        self.path = path
        self.conn = sqlite3.connect(path)
        self.conn.execute(
            "CREATE TABLE IF NOT EXISTS memory ("
            "id INTEGER PRIMARY KEY, scope TEXT, kind TEXT, tags TEXT, content TEXT)"
        )
        self.conn.commit()

    def add(self, scope: str, kind: str, tags: list[str], content: str) -> None:
        self.conn.execute(
            "INSERT INTO memory (scope, kind, tags, content) VALUES (?, ?, ?, ?)",
            (scope, kind, ",".join(tags), content),
        )
        self.conn.commit()

    def find(self, tags: list[str]) -> list[str]:
        rows = self.conn.execute("SELECT content, tags FROM memory").fetchall()
        return [
            content
            for content, stored_tags in rows
            if any(tag in stored_tags.split(",") for tag in tags)
        ]

    def close(self) -> None:
        self.conn.close()
