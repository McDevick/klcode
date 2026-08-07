import json
import re
from datetime import datetime, timezone
from pathlib import Path


_SENSITIVE_VALUE_RE = re.compile(
    r"(sk-[a-z0-9_-]+|ghp_[a-z0-9]+|AKIA[0-9a-z]{16}|api[_-]?key\s*[=:]|secret\s*[=:]|token\s*[=:]|password\s*[=:]|authorization\s*:\s*bearer|-----begin[ a-z0-9]*private key-----)",
    re.I,
)


def redact_value(key: str, value) -> object:
    if re.search(r"key|secret|token|credential|password|authorization", key, re.I):
        return "[REDACTED]"
    if key.lower() in {"command", "env", "environment", "credential_ref"}:
        return "[REDACTED]"
    if isinstance(value, dict):
        return redact_payload(value)
    if isinstance(value, list):
        return [redact_value(key, item) for item in value]
    if isinstance(value, str) and _SENSITIVE_VALUE_RE.search(value):
        return "[REDACTED]"
    return value


def redact_payload(payload: dict) -> dict:
    return {
        key: redact_value(key, value)
        for key, value in payload.items()
    }


class EventLogger:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def write(self, event: str, payload: dict, task_id: str = "") -> None:
        if not isinstance(payload, dict):
            raise TypeError("payload must be a dict")
        redacted = self._redact(payload)
        try:
            with self.path.open("a", encoding="utf-8") as f:
                f.write(
                    json.dumps(
                        {
                            "event": event,
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                            "task_id": task_id,
                            "payload": redacted,
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )
                f.flush()
        except OSError as exc:
            raise RuntimeError(f"failed to write audit log: {self.path}: {exc}") from exc

    def _redact(self, payload: dict) -> dict:
        return redact_payload(payload)

    def _redact_value(self, key: str, value) -> object:
        return redact_value(key, value)
