import json
from kl_server.core.event_logger import EventLogger


def test_event_logger_appends_and_redacts(tmp_path):
    logger = EventLogger(tmp_path / "audit.jsonl")
    logger.write("action", {"key": "sk-secret", "command": "pytest"})
    lines = (tmp_path / "audit.jsonl").read_text(encoding="utf-8").strip().splitlines()
    payload = json.loads(lines[0])["payload"]
    assert payload["key"] == "[REDACTED]"
