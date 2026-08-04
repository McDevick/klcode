import json
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import httpx
import pytest

from kl_server.hooks.manager import HookCommandError, HookManager


def make_script(tmp_path, source):
    script_dir = tmp_path / "hook scripts"
    script_dir.mkdir(exist_ok=True)
    script = script_dir / "hook.py"
    script.write_text(source, encoding="utf-8")
    return script


def make_command(tmp_path, source):
    script = make_script(tmp_path, source)
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
    script_dir = tmp_path / "hook scripts"
    script_dir.mkdir(exist_ok=True)
    first = script_dir / "first.py"
    first.write_text("print('first')", encoding="utf-8")
    second = script_dir / "second.py"
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


def test_command_hook_accepts_argv_list_with_spaces(tmp_path):
    script = make_script(tmp_path, "print('argv-ok')")
    manager = HookManager(
        {
            "event": [
                {
                    "type": "command",
                    "command": [sys.executable, str(script)],
                }
            ]
        }
    )

    assert manager.run("event", {}) == ["argv-ok"]


def test_command_hook_preserves_non_ascii_output(tmp_path):
    command = make_command(tmp_path, "print('中文')")
    manager = HookManager(
        {"event": [{"type": "command", "command": command}]}
    )

    assert manager.run("event", {}) == ["中文"]


class CaptureHook(BaseHTTPRequestHandler):
    received: list[dict] = []

    def do_POST(self):
        length = int(self.headers["Content-Length"])
        CaptureHook.received.append(json.loads(self.rfile.read(length)))
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"ok")

    def log_message(self, format, *args):
        pass


class FailHook(BaseHTTPRequestHandler):
    def do_POST(self):
        self.send_response(500)
        self.end_headers()
        self.wfile.write(b"server error")

    def log_message(self, format, *args):
        pass


def run_http_server(handler):
    server = HTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread


def test_http_hook_posts_payload():
    CaptureHook.received.clear()
    server, thread = run_http_server(CaptureHook)
    try:
        manager = HookManager(
            {
                "approval_request": [
                    {
                        "type": "http",
                        "url": f"http://127.0.0.1:{server.server_address[1]}/hook",
                    }
                ]
            }
        )

        output = manager.run("approval_request", {"task_id": "t1"})

        assert CaptureHook.received and CaptureHook.received[-1]["task_id"] == "t1"
        assert output == ["ok"]
    finally:
        server.shutdown()
        thread.join()
        server.server_close()


def test_http_hook_non_ok_response_is_ignored_with_error():
    server, thread = run_http_server(FailHook)
    try:
        manager = HookManager(
            {
                "event": [
                    {
                        "type": "http",
                        "url": f"http://127.0.0.1:{server.server_address[1]}/hook",
                    }
                ]
            }
        )

        output = manager.run("event", {})

        assert len(output) == 1
        assert output[0].startswith("hook error:")
        assert "500" in output[0]
    finally:
        server.shutdown()
        thread.join()
        server.server_close()


def test_http_hook_non_ok_response_aborts():
    server, thread = run_http_server(FailHook)
    try:
        manager = HookManager(
            {
                "event": [
                    {
                        "type": "http",
                        "url": f"http://127.0.0.1:{server.server_address[1]}/hook",
                    }
                ]
            },
            on_error="abort",
        )

        with pytest.raises(httpx.HTTPError):
            manager.run("event", {})
    finally:
        server.shutdown()
        thread.join()
        server.server_close()


def test_http_hook_missing_url_is_ignored_with_error():
    manager = HookManager(
        {"event": [{"type": "http"}]}
    )

    output = manager.run("event", {})

    assert len(output) == 1
    assert output[0].startswith("hook error:")
    assert "url" in output[0]


def test_http_hook_missing_url_aborts():
    manager = HookManager(
        {"event": [{"type": "http"}]},
        on_error="abort",
    )

    with pytest.raises(ValueError, match="url"):
        manager.run("event", {})


def test_unknown_event_returns_empty_outputs():
    assert HookManager({}).run("missing", {}) == []


def test_timeout_is_ignored_by_default(tmp_path):
    script = make_script(tmp_path, "import time; time.sleep(10)")
    manager = HookManager(
        {
            "slow": [
                {
                    "type": "command",
                    "command": [sys.executable, str(script)],
                }
            ]
        },
        timeout=0.05,
    )

    output = manager.run("slow", {})

    assert len(output) == 1
    assert output[0].startswith("hook error:")
    assert "timed out" in output[0]


def test_timeout_aborts(tmp_path):
    script = make_script(tmp_path, "import time; time.sleep(10)")
    manager = HookManager(
        {
            "slow": [
                {
                    "type": "command",
                    "command": [sys.executable, str(script)],
                }
            ]
        },
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

    with pytest.raises(HookCommandError):
        manager.run("bad", {})


def test_nonzero_exit_is_ignored_with_error_output(tmp_path):
    command = make_command(
        tmp_path,
        "import sys; print('bad-stdout'); print('bad stderr', file=sys.stderr); raise SystemExit(7)",
    )
    manager = HookManager(
        {"fail": [{"type": "command", "command": command}]}
    )

    output = manager.run("fail", {})

    assert len(output) == 1
    assert output[0].startswith("hook error:")
    assert "status 7" in output[0]
    assert "bad stderr" in output[0]
    assert "bad-stdout" not in output[0]


def test_nonzero_exit_aborts(tmp_path):
    command = make_command(
        tmp_path,
        "import sys; print('bad-stdout'); raise SystemExit(7)",
    )
    manager = HookManager(
        {"fail": [{"type": "command", "command": command}]},
        on_error="abort",
    )

    with pytest.raises(HookCommandError, match="status 7"):
        manager.run("fail", {})


def test_nonzero_exit_stderr_is_truncated(tmp_path):
    command = make_command(
        tmp_path,
        "import sys; print('x' * 2000, file=sys.stderr); raise SystemExit(2)",
    )
    manager = HookManager(
        {"fail": [{"type": "command", "command": command}]}
    )

    output = manager.run("fail", {})

    assert output[0].startswith("hook error:")
    assert "x" * 1000 in output[0]
    assert "x" * 1001 not in output[0]


def test_invalid_on_error_raises_value_error():
    with pytest.raises(ValueError, match="on_error"):
        HookManager({}, on_error="log")


@pytest.mark.parametrize("on_error", ["ignore", "abort"])
def test_hook_manager_rejects_non_dict_hooks(on_error):
    with pytest.raises(TypeError, match="hooks must be a dict"):
        HookManager(None, on_error=on_error)


def test_event_with_non_list_hooks_is_ignored_with_error():
    manager = HookManager({"event": None})

    output = manager.run("event", {})

    assert len(output) == 1
    assert output[0].startswith("hook error:")
    assert "must be a list" in output[0]


def test_event_with_non_list_hooks_aborts():
    manager = HookManager({"event": None}, on_error="abort")

    with pytest.raises(TypeError, match="must be a list"):
        manager.run("event", {})


def test_blank_command_is_ignored_with_error():
    manager = HookManager(
        {"event": [{"type": "command", "command": "   "}]}
    )

    output = manager.run("event", {})

    assert len(output) == 1
    assert output[0].startswith("hook error:")
    assert "blank" in output[0]


def test_blank_command_aborts():
    manager = HookManager(
        {"event": [{"type": "command", "command": "   "}]},
        on_error="abort",
    )

    with pytest.raises(ValueError, match="blank"):
        manager.run("event", {})


def test_missing_hook_type_is_ignored_with_error():
    manager = HookManager({"event": [{"command": "echo hi"}]})

    output = manager.run("event", {})

    assert len(output) == 1
    assert output[0].startswith("hook error:")
    assert "type" in output[0]


def test_malformed_hooks_are_ignored_with_errors():
    manager = HookManager({"event": [{"type": "command"}, 123]})

    output = manager.run("event", {})

    assert len(output) == 2
    assert all(item.startswith("hook error:") for item in output)


def test_malformed_hook_aborts():
    manager = HookManager({"event": [123]}, on_error="abort")

    with pytest.raises(ValueError, match="dict"):
        manager.run("event", {})
