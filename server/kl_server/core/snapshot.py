import shutil
from uuid import uuid4
from pathlib import Path


_MARKER = ".kl_snapshot"


class SnapshotManager:
    def __init__(self, workspace: str):
        self.workspace = Path(workspace)

    def create(self) -> Path:
        snapshot = Path(self.workspace.parent) / f"{self.workspace.name}.snapshot.{uuid4().hex[:8]}"
        shutil.copytree(self.workspace, snapshot, symlinks=True)
        (snapshot / _MARKER).write_text(str(self.workspace.resolve()), encoding="utf-8")
        return snapshot

    def restore(self, snapshot: Path) -> None:
        snapshot = Path(snapshot)
        if not snapshot.is_dir() or not (snapshot / _MARKER).is_file():
            raise ValueError("invalid snapshot")
        if (snapshot / _MARKER).read_text(encoding="utf-8") != str(self.workspace.resolve()):
            raise ValueError("snapshot does not belong to this workspace")
        for child in self.workspace.iterdir():
            if child.is_symlink() or child.is_file():
                child.unlink()
            elif child.is_dir():
                shutil.rmtree(child)
        for child in snapshot.iterdir():
            if child.name == _MARKER:
                continue
            shutil.move(str(child), self.workspace / child.name)
        (snapshot / _MARKER).unlink()
        shutil.rmtree(snapshot)
