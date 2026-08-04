import shutil
from pathlib import Path


class SnapshotManager:
    def __init__(self, workspace: str):
        self.workspace = Path(workspace)

    def create(self) -> Path:
        snapshot = Path(self.workspace.parent) / f"{self.workspace.name}.snapshot"
        if snapshot.exists():
            shutil.rmtree(snapshot)
        shutil.copytree(self.workspace, snapshot)
        return snapshot

    def restore(self, snapshot: Path) -> None:
        for child in self.workspace.iterdir():
            if child.is_dir():
                shutil.rmtree(child)
            else:
                child.unlink()
        for child in snapshot.iterdir():
            shutil.move(str(child), self.workspace / child.name)
