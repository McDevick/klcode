import json
import logging
import shlex
import subprocess

logger = logging.getLogger(__name__)


class HookManager:
    """Dispatch configured hooks for lifecycle events."""

    def __init__(
        self,
        hooks: dict[str, list[dict]],
        on_error: str = "ignore",
        timeout: float = 30.0,
    ):
        self.hooks = hooks
        self.on_error = on_error
        self.timeout = timeout

    def run(self, event: str, payload: dict) -> list[str]:
        outputs = []
        for hook in self.hooks.get(event, []):
            if hook.get("type") != "command":
                continue
            try:
                proc = subprocess.run(
                    shlex.split(hook["command"]),
                    input=json.dumps(payload),
                    text=True,
                    capture_output=True,
                    timeout=self.timeout,
                )
                outputs.append(proc.stdout.strip())
            except Exception as exc:
                if self.on_error == "abort":
                    raise
                logger.warning("Hook error for event %s: %s", event, exc)
                outputs.append(f"hook error: {exc}")
        return outputs
