import json
import re
from pathlib import Path


class EventLogger:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def write(self, event: str, payload: dict) -> None:
        redacted = self._redact(payload)
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"event": event, "payload": redacted}, ensure_ascii=False) + "\n")

    def _redact(self, payload: dict) -> dict:
        return {key: ("[REDACTED]" if re.search(r"key|secret|token", key, re.I) else value) for key, value in payload.items()}
