from pathlib import Path


class ScopeFence:
    def __init__(self, workspace: str):
        self.root = Path(workspace).resolve()

    def allow(self, path: Path | str) -> bool:
        candidate = Path(path).resolve()
        return candidate == self.root or self.root in candidate.parents
