"""Hook dispatch for lifecycle events.

Command hooks support two command forms:
- a list of argv strings, passed directly to subprocess without a shell;
- a string command, executed through the platform shell with ``shell=True``.

HTTP hooks POST the JSON payload to the configured URL.

String commands are trusted configuration and are interpreted by the platform
shell, so they should not be built from untrusted input.
"""

import json
import logging
import os
import subprocess

import httpx

logger = logging.getLogger(__name__)

MAX_ERROR_TEXT = 1000


class HookCommandError(RuntimeError):
    """Raised when a command hook exits with a non-zero status."""

    def __init__(self, returncode: int, stderr: str):
        self.returncode = returncode
        self.stderr = stderr
        super().__init__(
            f"command exited with status {returncode}: {_truncate(stderr)}"
        )


def _truncate(text: str, limit: int = MAX_ERROR_TEXT) -> str:
    text = text.strip()
    if len(text) <= limit:
        return text
    return f"{text[:limit]}..."


class HookManager:
    """Dispatch configured hooks for lifecycle events."""

    def __init__(
        self,
        hooks: dict[str, list[dict]],
        on_error: str = "ignore",
        timeout: float = 30.0,
    ):
        if not isinstance(hooks, dict):
            raise TypeError(
                f"hooks must be a dict, got {type(hooks).__name__}"
            )
        if on_error not in ("ignore", "abort"):
            raise ValueError("on_error must be 'ignore' or 'abort'")
        self.hooks = hooks
        self.on_error = on_error
        self.timeout = timeout

    def run(self, event: str, payload: dict) -> list[str]:
        outputs = []
        event_hooks = self.hooks.get(event, [])
        if not isinstance(event_hooks, list):
            exc = TypeError(
                f"hooks for event {event!r} must be a list, "
                f"got {type(event_hooks).__name__}"
            )
            if self.on_error == "abort":
                raise exc
            logger.warning("Hook error for event %s: %s", event, exc)
            return [f"hook error: {exc}"]

        for hook in event_hooks:
            try:
                if not isinstance(hook, dict):
                    raise ValueError(
                        f"hook must be a dict, got {type(hook).__name__}"
                    )
                if "type" not in hook:
                    raise ValueError("hook missing 'type'")
                hook_type = hook["type"]
                if hook_type not in ("command", "http"):
                    continue
                if hook_type == "command":
                    if "command" not in hook:
                        raise ValueError("command hook missing 'command'")
                    outputs.append(self._run_command(hook["command"], payload))
                else:
                    if "url" not in hook:
                        raise ValueError("http hook missing 'url'")
                    outputs.append(self._run_http(hook["url"], payload))
            except Exception as exc:
                if self.on_error == "abort":
                    raise
                logger.warning("Hook error for event %s: %s", event, exc)
                outputs.append(f"hook error: {exc}")
        return outputs

    def _run_command(self, command: object, payload: dict) -> str:
        if isinstance(command, str):
            if not command.strip():
                raise ValueError("command must not be blank")
            args = command
            shell = True
        elif (
            isinstance(command, list)
            and command
            and all(isinstance(item, str) for item in command)
        ):
            args = command
            shell = False
        else:
            raise ValueError(
                "command must be a non-empty list of argv strings or a string"
            )

        proc = subprocess.run(
            args,
            shell=shell,
            env=self._command_env(),
            input=json.dumps(payload),
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            timeout=self.timeout,
        )
        if proc.returncode != 0:
            raise HookCommandError(proc.returncode, proc.stderr)
        return proc.stdout.strip()

    def _run_http(self, url: object, payload: dict) -> str:
        if not isinstance(url, str) or not url.strip():
            raise ValueError("http hook 'url' must be a non-empty string")
        response = httpx.post(url, json=payload, timeout=self.timeout)
        response.raise_for_status()
        return _truncate(response.text)

    def _command_env(self) -> dict[str, str]:
        env = os.environ.copy()
        env["PYTHONUTF8"] = "1"
        env["PYTHONIOENCODING"] = "utf-8"
        return env
