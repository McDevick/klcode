import pytest
from pathlib import Path
from kl_server.core.snapshot import SnapshotManager


def test_snapshot_and_rollback(tmp_path):
    target = tmp_path / "work"
    target.mkdir()
    (target / "a.txt").write_text("before", encoding="utf-8")
    manager = SnapshotManager(str(target))
    snapshot = manager.create()
    (target / "a.txt").write_text("after", encoding="utf-8")
    manager.restore(snapshot)
    assert (target / "a.txt").read_text(encoding="utf-8") == "before"


def test_snapshot_restores_nested_and_added_files(tmp_path):
    target = tmp_path / "work"
    target.mkdir()
    sub = target / "sub"
    sub.mkdir()
    (sub / "a.txt").write_text("before", encoding="utf-8")
    manager = SnapshotManager(str(target))
    snapshot = manager.create()
    (sub / "a.txt").write_text("after", encoding="utf-8")
    (target / "new.txt").write_text("new", encoding="utf-8")
    manager.restore(snapshot)
    assert (sub / "a.txt").read_text(encoding="utf-8") == "before"
    assert not (target / "new.txt").exists()


def test_restore_missing_snapshot_does_not_clear_workspace(tmp_path):
    target = tmp_path / "work"
    target.mkdir()
    (target / "a.txt").write_text("keep", encoding="utf-8")
    manager = SnapshotManager(str(target))
    with pytest.raises(ValueError):
        manager.restore(tmp_path / "missing")
    assert (target / "a.txt").read_text(encoding="utf-8") == "keep"


def test_restore_rejects_repeated_restore(tmp_path):
    target = tmp_path / "work"
    target.mkdir()
    (target / "a.txt").write_text("before", encoding="utf-8")
    manager = SnapshotManager(str(target))
    snapshot = manager.create()
    manager.restore(snapshot)
    with pytest.raises(ValueError):
        manager.restore(snapshot)


def test_snapshot_preserves_marker_named_workspace_file(tmp_path):
    target = tmp_path / "work"
    target.mkdir()
    (target / ".kl_snapshot").write_text("real content", encoding="utf-8")
    manager = SnapshotManager(str(target))
    snapshot = manager.create()
    (target / ".kl_snapshot").write_text("changed", encoding="utf-8")
    manager.restore(snapshot)
    assert (target / ".kl_snapshot").read_text(encoding="utf-8") == "real content"


def test_restore_rejects_wrong_workspace(tmp_path):
    first = tmp_path / "first"
    second = tmp_path / "second"
    first.mkdir()
    second.mkdir()
    (first / "a.txt").write_text("before", encoding="utf-8")
    (second / "b.txt").write_text("keep", encoding="utf-8")
    snapshot = SnapshotManager(str(first)).create()
    with pytest.raises(ValueError):
        SnapshotManager(str(second)).restore(snapshot)
    assert (second / "b.txt").read_text(encoding="utf-8") == "keep"
