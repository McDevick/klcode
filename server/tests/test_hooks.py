import subprocess
import sys

import pytest

from kl_server.hooks.manager import HookManager


def make_command(tmp_path, source):
    script = tmp_path / "hook.py"
    script.write_text(source, encoding="utf-8")
    return f'"{sys.executable}" "{script}"'


def test_command_hook_receives_event(tmp_path):
    command = make_command(
        tmp_path,
        "import sys, json; print(json.load(sys.stdin)['event'])",
    )
    manager = HookManager({"task_start": [{"type": "command", "command": command}]})

    output = manager.run("task_start", {"event": "task_start", "task_id": "t1"})

    assert output[0] == "task_start"


def test_command_hook_outputs_preserve_order(tmp_path):
    first = tmp_path / "first.py"
    first.write_text("print('first')", encoding="utf-8")
    second = tmp_path / "second.py"
    second.write_text("print('second')", encoding="utf-8")
    manager = HookManager(
        {
            "event": [
                {"type": "command", "command": f'"{sys.executable}" "{first}"'},
                {"type": "command", "command": f'"{sys.executable}" "{second}"'},
            ]
        }
    )

    assert manager.run("event", {}) == ["first", "second"]


def test_unknown_event_returns_empty_outputs():
    assert HookManager({}).run("missing", {}) == []


def test_timeout_is_ignored_by_default(tmp_path):
    command = make_command(tmp_path, "import time; time.sleep(10)")
    manager = HookManager(
        {"slow": [{"type": "command", "command": command}]},
        timeout=0.05,
    )

    output = manager.run("slow", {})

    assert len(output) == 1
    assert output[0].startswith("hook error:")
    assert "timed out" in output[0]


def test_timeout_aborts(tmp_path):
    command = make_command(tmp_path, "import time; time.sleep(10)")
    manager = HookManager(
        {"slow": [{"type": "command", "command": command}]},
        on_error="abort",
        timeout=0.05,
    )

    with pytest.raises(subprocess.TimeoutExpired):
        manager.run("slow", {})


def test_missing_command_is_ignored_by_default():
    manager = HookManager(
        {"bad": [{"type": "command", "command": "kl_server_missing_hook_command"}]}
    )

    output = manager.run("bad", {})

    assert len(output) == 1
    assert output[0].startswith("hook error:")


def test_missing_command_abort_reraises():
    manager = HookManager(
        {"bad": [{"type": "command", "command": "kl_server_missing_hook_command"}]},
        on_error="abort",
    )

    with pytest.raises(OSError):
        manager.run("bad", {})
