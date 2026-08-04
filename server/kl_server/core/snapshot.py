import shutil
from pathlib import Path
from uuid import uuid4


class SnapshotManager:
    def __init__(self, workspace: str):
        self.workspace = Path(workspace)

    def create(self) -> Path:
        snapshot = Path(self.workspace.parent) / f"{self.workspace.name}.snapshot.{uuid4().hex[:8]}"
        meta = snapshot.with_name(snapshot.name + ".meta")
        if snapshot.exists() or meta.exists():
            raise FileExistsError("snapshot path already exists")
        try:
            shutil.copytree(self.workspace, snapshot, symlinks=True)
            meta.write_text(str(self.workspace.resolve()), encoding="utf-8")
        except Exception:
            shutil.rmtree(snapshot, ignore_errors=True)
            meta.unlink(missing_ok=True)
            raise
        return snapshot

    def restore(self, snapshot: Path) -> None:
        snapshot = Path(snapshot)
        meta = snapshot.with_name(snapshot.name + ".meta")
        if not snapshot.is_dir() or not meta.is_file():
            raise ValueError("invalid snapshot")
        if meta.read_text(encoding="utf-8") != str(self.workspace.resolve()):
            raise ValueError("snapshot does not belong to this workspace")
        backup = self.workspace.parent / f"{self.workspace.name}.restore.{uuid4().hex[:8]}"
        if backup.exists():
            raise FileExistsError("restore backup path already exists")
        try:
            shutil.move(str(self.workspace), str(backup))
            shutil.move(str(snapshot), str(self.workspace))
        except Exception:
            if not self.workspace.exists() and backup.exists():
                shutil.move(str(backup), str(self.workspace))
            raise
        finally:
            shutil.rmtree(backup, ignore_errors=True)
            meta.unlink(missing_ok=True)
