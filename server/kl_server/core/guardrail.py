from pathlib import Path


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


from kl_server.models.action import Action


class DangerClassifier:
    CRITICAL_PATTERNS = ["rm -rf /", "format c:", "drop database", "git push --force"]

    def classify(self, action: Action) -> str:
        command = " ".join(str(v) for v in action.args.values()).lower()
        if any(pattern in command for pattern in self.CRITICAL_PATTERNS):
            return "critical"
        if action.tool == "delete_file":
            return "dangerous"
        return "normal"
