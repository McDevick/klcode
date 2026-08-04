import re
from pathlib import Path

from kl_server.models.action import Action


class ScopeFence:
    def __init__(self, workspace: str):
        self.root = Path(workspace).resolve()

    def allow(self, path: Path | str) -> bool:
        try:
            raw = Path(path)
            if isinstance(path, str) and not path:
                return False
            if not str(raw) or "\x00" in str(raw):
                return False
            if raw.drive and not raw.root:
                return False
            candidate = raw.resolve() if raw.is_absolute() else (self.root / raw).resolve()
        except (OSError, ValueError, RuntimeError, TypeError):
            return False
        return candidate == self.root or self.root in candidate.parents


class DangerClassifier:
    COMMAND_TOOLS = {"run_command", "run_tests", "run_lint", "typecheck"}
    CRITICAL_PATTERNS = [
        "rm -rf /",
        "rm -fr /",
        "rm -r -f /",
        "rm -f -r /",
        "format c:",
        "drop database",
        "git push --force",
        "git push -f",
        "remove-item -recurse -force",
    ]

    def classify(self, action: Action) -> str:
        if action.tool == "delete_file":
            return "dangerous"
        if action.tool not in self.COMMAND_TOOLS:
            return "normal"
        raw_command = action.args.get("command") or ""
        command = re.sub(r"\s+", " ", str(raw_command)).strip().lower()
        if any(pattern in command for pattern in self.CRITICAL_PATTERNS):
            return "critical"
        return "normal"
