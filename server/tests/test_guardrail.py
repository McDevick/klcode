import os
from pathlib import Path

import pytest

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


def test_additional_dangerous_variants_are_critical():
    classifier = DangerClassifier()
    for command in [
        "rm -rf -- /",
        "rm --recursive --force /",
        "Remove-Item -Force -Recurse C:\\",
        "git push --force origin main",
    ]:
        action = Action(tool="run_command", args={"command": command}, task_id="t1")
        assert classifier.classify(action) == "critical"


def test_classifier_uses_raw_command():
    classifier = DangerClassifier()
    action = Action(tool="run_command", args={}, raw_command="rm -rf /", task_id="t1")
    assert classifier.classify(action) == "critical"


def test_classifier_checks_both_command_sources():
    classifier = DangerClassifier()
    action = Action(tool="run_command", args={"command": "rm -rf /"}, raw_command="pytest", task_id="t1")
    assert classifier.classify(action) == "critical"


def test_git_c_dir_push_force_is_critical():
    classifier = DangerClassifier()
    action = Action(tool="run_command", args={"command": "git -C repo push -f"}, task_id="t1")
    assert classifier.classify(action) == "critical"


from kl_server.core.guardrail import ApprovalRequest, HITLManager


def test_hitl_approve_and_reject():
    manager = HITLManager()
    req = manager.request("a1", "run_command", "rm -rf /")
    assert req.state == "pending"
    assert manager.approve("a1") == "approved"
    assert manager.reject("a2") == "rejected"


def test_hitl_prevents_resolved_request_reopen():
    manager = HITLManager()
    manager.request("a1", "run_command", "rm -rf /")
    manager.reject("a1")
    with pytest.raises(ValueError):
        manager.request("a1", "run_command", "rm -rf /")


def test_hitl_approve_unknown_raises():
    manager = HITLManager()
    with pytest.raises(ValueError):
        manager.approve("missing")


def test_hitl_transitions_are_idempotent_and_locked():
    manager = HITLManager()
    manager.request("a1", "run_command", "pytest")
    assert manager.approve("a1") == "approved"
    assert manager.approve("a1") == "approved"
    with pytest.raises(ValueError):
        manager.reject("a1")

    manager.request("a2", "run_command", "pytest")
    assert manager.reject("a2") == "rejected"
    assert manager.reject("a2") == "rejected"
    with pytest.raises(ValueError):
        manager.approve("a2")


from kl_server.core.guardrail import DangerClassifier, Guardrail, HITLManager, ScopeFence
from kl_server.core.sandbox import SandboxPolicy
from kl_server.models.action import Action


def test_guardrail_blocks_outside_scope(tmp_path):
    guardrail = Guardrail(
        scope=ScopeFence(str(tmp_path)),
        sandbox=SandboxPolicy(allow=["pytest"], deny=["rm"]),
        danger=DangerClassifier(),
        hitl=HITLManager(),
    )
    action = Action(tool="read_file", args={"path": "../outside.py"}, task_id="t1")
    decision = guardrail.check(action)
    assert decision == "rejected"


def test_guardrail_rejects_denied_command(tmp_path):
    guardrail = Guardrail(
        scope=ScopeFence(str(tmp_path)),
        sandbox=SandboxPolicy(allow=["pytest"], deny=["rm"]),
        danger=DangerClassifier(),
        hitl=HITLManager(),
    )
    action = Action(tool="run_command", args={"command": "rm -rf ."}, task_id="t1")
    assert guardrail.check(action) == "rejected"


def test_guardrail_requires_approval_for_dangerous(tmp_path):
    hitl = HITLManager()
    guardrail = Guardrail(
        scope=ScopeFence(str(tmp_path)),
        sandbox=SandboxPolicy(allow=[], deny=[]),
        danger=DangerClassifier(),
        hitl=hitl,
    )
    critical = Action(tool="run_command", args={"command": "rm -rf /"}, task_id="t1")
    delete = Action(tool="delete_file", args={"path": "a.txt"}, task_id="t2")
    assert guardrail.check(critical) == "requires_approval"
    assert guardrail.check(delete) == "requires_approval"
    assert hitl.requests


def test_guardrail_checks_raw_command_and_other_paths(tmp_path):
    guardrail = Guardrail(
        scope=ScopeFence(str(tmp_path)),
        sandbox=SandboxPolicy(allow=[], deny=["rm"]),
        danger=DangerClassifier(),
        hitl=HITLManager(),
    )
    raw = Action(tool="run_command", args={}, raw_command="rm -rf .", task_id="t1")
    assert guardrail.check(raw) == "rejected"
    patch = Action(tool="apply_patch", args={"patch": "--- ../outside.py\n+++ b\n@@ -1 +1 @@\n-x\n+y\n"}, task_id="t2")
    assert guardrail.check(patch) == "rejected"
    git = Action(tool="git_commit", args={"paths": ["../outside.py"]}, task_id="t3")
    assert guardrail.check(git) == "rejected"


def test_guardrail_allows_safe_action(tmp_path):
    guardrail = Guardrail(
        scope=ScopeFence(str(tmp_path)),
        sandbox=SandboxPolicy(allow=[], deny=["rm"]),
        danger=DangerClassifier(),
        hitl=HITLManager(),
    )
    action = Action(tool="read_file", args={"path": "a.py"}, task_id="t1")
    assert guardrail.check(action) == "allowed"


def test_guardrail_checks_all_command_sources(tmp_path):
    guardrail = Guardrail(
        scope=ScopeFence(str(tmp_path)),
        sandbox=SandboxPolicy(allow=[], deny=["rm"]),
        danger=DangerClassifier(),
        hitl=HITLManager(),
    )
    action = Action(tool="run_command", args={"command": "rm -rf ."}, raw_command="pytest", task_id="t1")
    assert guardrail.check(action) == "rejected"


def test_guardrail_uses_unique_approval_keys(tmp_path):
    hitl = HITLManager()
    guardrail = Guardrail(
        scope=ScopeFence(str(tmp_path)),
        sandbox=SandboxPolicy(allow=[], deny=[]),
        danger=DangerClassifier(),
        hitl=hitl,
    )
    first = Action(tool="delete_file", args={"path": "a.txt"}, task_id="t1")
    second = Action(tool="delete_file", args={"path": "b.txt"}, task_id="t1")
    assert guardrail.check(first) == "requires_approval"
    assert guardrail.check(second) == "requires_approval"
    assert len(hitl.requests) == 2


def test_guardrail_fails_closed_on_bad_patch(tmp_path):
    guardrail = Guardrail(
        scope=ScopeFence(str(tmp_path)),
        sandbox=SandboxPolicy(allow=[], deny=[]),
        danger=DangerClassifier(),
        hitl=HITLManager(),
    )
    action = Action(tool="apply_patch", args={"patch": 123}, task_id="t1")
    assert guardrail.check(action) == "rejected"


from kl_server.core.guardrail import DangerClassifier, Guardrail, HITLManager, ScopeFence
from kl_server.core.sandbox import SandboxPolicy
from kl_server.models.action import Action


def test_unmanaged_mode_escalates_write_to_approval(tmp_path):
    guardrail = Guardrail(
        scope=ScopeFence(str(tmp_path)),
        sandbox=SandboxPolicy(allow=[], deny=["rm"]),
        danger=DangerClassifier(),
        hitl=HITLManager(),
        workspace_mode="unmanaged",
    )
    action = Action(tool="write_file", args={"path": "a.py", "content": "x"}, task_id="t1")
    assert guardrail.check(action) == "requires_approval"


def test_managed_mode_keeps_write_normal(tmp_path):
    guardrail = Guardrail(
        scope=ScopeFence(str(tmp_path)),
        sandbox=SandboxPolicy(allow=[], deny=["rm"]),
        danger=DangerClassifier(),
        hitl=HITLManager(),
        workspace_mode="managed",
    )
    action = Action(tool="write_file", args={"path": "a.py", "content": "x"}, task_id="t1")
    assert guardrail.check(action) == "allowed"


def test_delete_file_always_requires_approval(tmp_path):
    guardrail = Guardrail(
        scope=ScopeFence(str(tmp_path)),
        sandbox=SandboxPolicy(allow=[], deny=["rm"]),
        danger=DangerClassifier(),
        hitl=HITLManager(),
        workspace_mode="managed",
    )
    action = Action(tool="delete_file", args={"path": "a.txt"}, task_id="t1")
    assert guardrail.check(action) == "requires_approval"


def test_unmanaged_escalates_command_and_patch(tmp_path):
    guardrail = Guardrail(
        scope=ScopeFence(str(tmp_path)),
        sandbox=SandboxPolicy(allow=[], deny=["rm"]),
        danger=DangerClassifier(),
        hitl=HITLManager(),
        workspace_mode="unmanaged",
    )
    run = Action(tool="run_command", args={"command": "pytest -q"}, task_id="t1")
    patch = Action(tool="apply_patch", args={"patch": "--- a.txt\n+++ b.txt\n@@ -1 +1 @@\n-x\n+y\n"}, task_id="t2")
    assert guardrail.check(run) == "requires_approval"
    assert guardrail.check(patch) == "requires_approval"


def test_git_commit_requires_approval_in_managed_mode(tmp_path):
    guardrail = Guardrail(
        scope=ScopeFence(str(tmp_path)),
        sandbox=SandboxPolicy(allow=[], deny=["rm"]),
        danger=DangerClassifier(),
        hitl=HITLManager(),
        workspace_mode="managed",
    )
    action = Action(tool="git_commit", args={"paths": ["a.txt"]}, task_id="t1")
    assert guardrail.check(action) == "requires_approval"


def test_unknown_workspace_mode_is_rejected(tmp_path):
    with pytest.raises(ValueError):
        Guardrail(
            scope=ScopeFence(str(tmp_path)),
            sandbox=SandboxPolicy(allow=[], deny=[]),
            danger=DangerClassifier(),
            hitl=HITLManager(),
            workspace_mode="unknown",
        )
