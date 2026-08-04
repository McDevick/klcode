import shutil
from pathlib import Path
from uuid import uuid4


class SnapshotManager:
    def __init__(self, workspace: str):
        self.workspace = Path(workspace)

    def create(self) -> Path:
        snapshot = Path(self.workspace.parent) / f"{self.workspace.name}.snapshot.{uuid4().hex[:8]}"
        try:
            shutil.copytree(self.workspace, snapshot, symlinks=True)
        except Exception:
            shutil.rmtree(snapshot, ignore_errors=True)
            raise
        meta = snapshot.with_name(snapshot.name + ".meta")
        meta.write_text(str(self.workspace.resolve()), encoding="utf-8")
        return snapshot

    def restore(self, snapshot: Path) -> None:
        snapshot = Path(snapshot)
        meta = snapshot.with_name(snapshot.name + ".meta")
        if not snapshot.is_dir() or not meta.is_file():
            raise ValueError("invalid snapshot")
        if meta.read_text(encoding="utf-8") != str(self.workspace.resolve()):
            raise ValueError("snapshot does not belong to this workspace")
        for child in self.workspace.iterdir():
            if child.is_symlink() or child.is_file():
                child.unlink()
            elif child.is_dir():
                shutil.rmtree(child)
        for child in snapshot.iterdir():
            shutil.move(str(child), self.workspace / child.name)
        meta.unlink()
        shutil.rmtree(snapshot)
