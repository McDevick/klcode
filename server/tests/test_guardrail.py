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
