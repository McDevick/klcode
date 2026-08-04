import json
import pytest
from kl_server.core.event_logger import EventLogger


def test_event_logger_appends_and_redacts(tmp_path):
    logger = EventLogger(tmp_path / "audit.jsonl")
    logger.write("action", {"key": "sk-secret", "command": "pytest"})
    lines = (tmp_path / "audit.jsonl").read_text(encoding="utf-8").strip().splitlines()
    payload = json.loads(lines[0])["payload"]
    assert payload["key"] == "[REDACTED]"


def test_event_logger_redacts_nested_and_sensitive_values(tmp_path):
    logger = EventLogger(tmp_path / "audit.jsonl")
    logger.write(
        "action",
        {
            "nested": {"api_key": "sk-nested"},
            "items": [{"token": "abc"}],
            "command": "echo api_key=top-secret",
            "env": {"OPENAI_API_KEY": "sk-env"},
        },
    )
    payload = json.loads((tmp_path / "audit.jsonl").read_text(encoding="utf-8").strip().splitlines()[0])["payload"]
    assert payload["nested"]["api_key"] == "[REDACTED]"
    assert payload["items"][0]["token"] == "[REDACTED]"
    assert payload["command"] == "[REDACTED]"
    assert payload["env"] == "[REDACTED]"


def test_event_logger_appends_multiple_events_in_order(tmp_path):
    logger = EventLogger(tmp_path / "audit.jsonl")
    logger.write("first", {"a": 1})
    logger.write("second", {"b": 2})
    lines = (tmp_path / "audit.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert [json.loads(line)["event"] for line in lines] == ["first", "second"]


def test_event_logger_rejects_non_dict_payload(tmp_path):
    logger = EventLogger(tmp_path / "audit.jsonl")
    with pytest.raises(TypeError):
        logger.write("action", "not-a-dict")
