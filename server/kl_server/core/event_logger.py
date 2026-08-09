import json
import re
from datetime import datetime, timezone
from pathlib import Path


_SENSITIVE_VALUE_RE = re.compile(
    r"(sk-[a-z0-9_-]+|ghp_[a-z0-9]+|AKIA[0-9a-z]{16}|-----begin[ a-z0-9]*private key-----)",
    re.I,
)
_LABEL_SECRET_RE = re.compile(
    r"\b(api[_-]?key|secret|token|password)\s*([=:])\s*[^\s\"']+",
    re.I,
)
_AUTH_RE = re.compile(
    r"authorization\s*:\s*bearer\s+[^\s\"']+",
    re.I,
)
_SECRET_FLAG_RE = re.compile(
    r"(--(?:token|password|secret|api[_-]?key|authorization)\s+)([^\s\"']+)",
    re.I,
)
_ENV_SECRET_RE = re.compile(
    r"\b(?:OPENAI|ANTHROPIC|AWS|AZURE|GITHUB|GOOGLE|HF|HUGGING|TELEGRAM|DISCORD|SLACK|GEMINI)_[A-Z0-9_]*\s*=\s*[^\s\"']+",
    re.I,
)


def _replace_label_secret(match: re.Match[str]) -> str:
    return f"{match.group(1)}{match.group(2)}[REDACTED]"


def _replace_auth(match: re.Match[str]) -> str:
    return "authorization: [REDACTED]"


def _redact_text(text: str) -> str:
    redacted = _SENSITIVE_VALUE_RE.sub("[REDACTED]", text)
    redacted = _LABEL_SECRET_RE.sub(_replace_label_secret, redacted)
    redacted = _AUTH_RE.sub(_replace_auth, redacted)
    redacted = _SECRET_FLAG_RE.sub(r"\1[REDACTED]", redacted)
    redacted = _ENV_SECRET_RE.sub("[REDACTED]", redacted)
    return redacted


def _has_secret(text: str) -> bool:
    return any(
        pattern.search(text)
        for pattern in (
            _SENSITIVE_VALUE_RE,
            _LABEL_SECRET_RE,
            _AUTH_RE,
            _SECRET_FLAG_RE,
            _ENV_SECRET_RE,
        )
    )


def redact_value(key: str, value) -> object:
    if re.search(r"key|secret|token|credential|password|authorization", key, re.I):
        return "[REDACTED]"
    if key.lower() in {"env", "environment", "credential_ref"}:
        return "[REDACTED]"
    if isinstance(value, dict):
        return redact_payload(value)
    if isinstance(value, list):
        return [redact_value(key, item) for item in value]
    if isinstance(value, str) and _has_secret(value):
        return _redact_text(value)
    return value


def redact_payload(payload: dict) -> dict:
    return {
        key: redact_value(key, value)
        for key, value in payload.items()
    }


def _history_filename(task_id: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_-]+", "_", task_id).strip("_")
    return f"{safe or 'task'}.jsonl"


class EventLogger:
    def __init__(self, path: Path, history_dir: Path | None = None):
        self.path = path
        self.history_dir = Path(history_dir) if history_dir is not None else None
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.history_dir is not None:
            self.history_dir.mkdir(parents=True, exist_ok=True)

    def history_path(self, task_id: str) -> Path | None:
        if self.history_dir is None or not task_id:
            return None
        return self.history_dir / _history_filename(task_id)

    def write(self, event: str, payload: dict, task_id: str = "") -> None:
        if not isinstance(payload, dict):
            raise TypeError("payload must be a dict")
        redacted = self._redact(payload)
        record = {
            "event": event,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "task_id": task_id,
            "payload": redacted,
        }
        try:
            with self.path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
                f.flush()
            history_path = self.history_path(task_id)
            if history_path is not None:
                with history_path.open("a", encoding="utf-8") as f:
                    f.write(json.dumps(record, ensure_ascii=False) + "\n")
                    f.flush()
        except OSError as exc:
            raise RuntimeError(f"failed to write audit log: {self.path}: {exc}") from exc

    def delete_task_history(self, task_id: str) -> None:
        history_path = self.history_path(task_id)
        if history_path is not None:
            history_path.unlink(missing_ok=True)

    def _redact(self, payload: dict) -> dict:
        return redact_payload(payload)

    def _redact_value(self, key: str, value) -> object:
        return redact_value(key, value)