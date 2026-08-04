from pathlib import Path


class ScopeFence:
    def __init__(self, workspace: str):
        self.root = Path(workspace).resolve()

    def allow(self, path: Path | str) -> bool:
        try:
            raw = Path(path)
            candidate = raw.resolve() if raw.is_absolute() else (self.root / raw).resolve()
        except (OSError, ValueError, RuntimeError, TypeError):
            return False
        return candidate == self.root or self.root in candidate.parents
