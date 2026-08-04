import os
from pathlib import Path

from kl_server.core.guardrail import ScopeFence


def test_scope_fence_allows_inside_and_blocks_outside(tmp_path):
    fence = ScopeFence(str(tmp_path))
    inside = tmp_path / "a.py"
    outside = tmp_path.parent / "outside.py"
    assert fence.allow(inside) is True
    assert fence.allow(outside) is False


def test_scope_fence_allows_root_and_relative_paths(tmp_path):
    fence = ScopeFence(str(tmp_path))
    assert fence.allow(tmp_path) is True
    assert fence.allow("a.py") is True
    assert fence.allow("../outside") is False


def test_scope_fence_rejects_sibling_prefix(tmp_path):
    fence = ScopeFence(str(tmp_path))
    sibling = tmp_path.parent / (tmp_path.name + "2")
    assert fence.allow(sibling) is False


def test_scope_fence_relative_path_does_not_depend_on_cwd(tmp_path, monkeypatch):
    sub = tmp_path / "sub"
    sub.mkdir()
    monkeypatch.chdir(sub)
    fence = ScopeFence(str(tmp_path))
    assert fence.allow("a.py") is True
    assert fence.allow("../outside") is False


def test_scope_fence_fails_closed_on_invalid_path(tmp_path):
    fence = ScopeFence(str(tmp_path))
    assert fence.allow(123) is False
    assert fence.allow("") is False
    assert fence.allow("a\x00b") is False


def test_scope_fence_rejects_windows_drive_relative_path(tmp_path):
    if os.name != "nt":
        return
    fence = ScopeFence(str(tmp_path))
    assert fence.allow("C:outside") is False


from kl_server.core.guardrail import DangerClassifier
from kl_server.models.action import Action


def test_dangerous_rm_is_critical():
    classifier = DangerClassifier()
    action = Action(tool="run_command", args={"command": "rm -rf /"}, task_id="t1")
    assert classifier.classify(action) == "critical"


def test_safe_command_is_normal():
    classifier = DangerClassifier()
    action = Action(tool="run_command", args={"command": "pytest"}, task_id="t1")
    assert classifier.classify(action) == "normal"


def test_delete_file_is_dangerous():
    classifier = DangerClassifier()
    action = Action(tool="delete_file", args={"path": "a.txt"}, task_id="t1")
    assert classifier.classify(action) == "dangerous"


def test_dangerous_command_variants_are_critical():
    classifier = DangerClassifier()
    for command in ["rm -fr /", "rm -r -f /", "git push -f origin main"]:
        action = Action(tool="run_command", args={"command": command}, task_id="t1")
        assert classifier.classify(action) == "critical"


def test_non_command_tools_are_not_misclassified():
    classifier = DangerClassifier()
    write = Action(tool="write_file", args={"path": "a.txt", "content": "rm -rf /"}, task_id="t1")
    patch = Action(tool="apply_patch", args={"patch": "drop database"}, task_id="t1")
    assert classifier.classify(write) == "normal"
    assert classifier.classify(patch) == "normal"
