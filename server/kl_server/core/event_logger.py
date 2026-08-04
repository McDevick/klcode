import json
import re
from datetime import datetime, timezone
from pathlib import Path


class EventLogger:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def write(self, event: str, payload: dict) -> None:
        if not isinstance(payload, dict):
            raise TypeError("payload must be a dict")
        redacted = self._redact(payload)
        with self.path.open("a", encoding="utf-8") as f:
            f.write(
                json.dumps(
                    {
                        "event": event,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "payload": redacted,
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )

    def _redact(self, payload: dict) -> dict:
        return {
            key: self._redact_value(key, value)
            for key, value in payload.items()
        }

    def _redact_value(self, key: str, value) -> object:
        if re.search(r"key|secret|token|credential|password|authorization", key, re.I):
            return "[REDACTED]"
        if key.lower() in {"command", "env", "environment", "credential_ref"}:
            return "[REDACTED]"
        if isinstance(value, dict):
            return self._redact(value)
        if isinstance(value, list):
            return [self._redact_value(key, item) for item in value]
        if isinstance(value, str) and re.search(r"(sk-[a-z0-9_-]+|api[_-]?key\s*[=:]|secret\s*[=:])", value, re.I):
            return "[REDACTED]"
        return value
