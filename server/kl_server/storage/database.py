import sqlite3
from pathlib import Path

from kl_server.models.task import Session, Task, TaskStatus


class Database:
    def __init__(self, path: Path):
        self.conn = sqlite3.connect(path)
        self.conn.execute(
            "CREATE TABLE IF NOT EXISTS sessions (id TEXT PRIMARY KEY, workspace TEXT, name TEXT, provider TEXT, model TEXT, status TEXT)"
        )
        self.conn.execute(
            "CREATE TABLE IF NOT EXISTS tasks (id TEXT PRIMARY KEY, session_id TEXT, description TEXT, status TEXT)"
        )
        self.conn.commit()
