from pathlib import Path

import pytest
from kl_server.tools.base import ToolContext
from kl_server.tools.builtin.filesystem import ListDirTool, ReadFileTool, WriteFileTool
from kl_server.tools.builtin.search import GlobTool, GrepTool


@pytest.mark.asyncio
async def test_write_read_list(tmp_path):
    ctx = ToolContext(workspace=str(tmp_path))
    write = await WriteFileTool().execute({"path": "a.txt", "content": "hello"}, ctx)
    read = await ReadFileTool().execute({"path": "a.txt"}, ctx)
    listed = await ListDirTool().execute({}, ctx)
    assert write.ok and read.output == "hello" and "a.txt" in listed.output


@pytest.mark.asyncio
async def test_grep_and_glob(tmp_path):
    ctx = ToolContext(workspace=str(tmp_path))
    (tmp_path / "a.py").write_text("def add(): pass", encoding="utf-8")
    grep = await GrepTool().execute({"pattern": "def add", "path": "."}, ctx)
    glob = await GlobTool().execute({"pattern": "*.py"}, ctx)
    assert "a.py" in grep.output and "a.py" in glob.output


@pytest.mark.asyncio
async def test_read_and_write_reject_outside_workspace(tmp_path):
    ctx = ToolContext(workspace=str(tmp_path))
    read = await ReadFileTool().execute({"path": "../outside.txt"}, ctx)
    write = await WriteFileTool().execute({"path": "../outside.txt", "content": "x"}, ctx)
    assert not read.ok and "outside workspace" in read.error
    assert not write.ok


@pytest.mark.asyncio
async def test_glob_does_not_escape_workspace(tmp_path):
    outside_dir = tmp_path.parent / "outside"
    outside_dir.mkdir(exist_ok=True)
    (outside_dir / "leak.txt").write_text("leak", encoding="utf-8")
    ctx = ToolContext(workspace=str(tmp_path))
    result = await GlobTool().execute({"pattern": str(Path("..") / "outside" / "*.txt")}, ctx)
    assert "leak.txt" not in result.output


@pytest.mark.asyncio
async def test_grep_respects_path(tmp_path):
    (tmp_path / "root.txt").write_text("needle", encoding="utf-8")
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "match.txt").write_text("needle", encoding="utf-8")
    ctx = ToolContext(workspace=str(tmp_path))
    result = await GrepTool().execute({"pattern": "needle", "path": "sub"}, ctx)
    assert str(Path("sub") / "match.txt") in result.output
    assert "root.txt" not in result.output


@pytest.mark.asyncio
async def test_read_missing_file_returns_error(tmp_path):
    ctx = ToolContext(workspace=str(tmp_path))
    result = await ReadFileTool().execute({"path": "missing.txt"}, ctx)
    assert not result.ok
    assert result.error


@pytest.mark.asyncio
async def test_read_non_utf8_file_returns_error(tmp_path):
    (tmp_path / "binary.bin").write_bytes(b"\xff\xfe")
    ctx = ToolContext(workspace=str(tmp_path))
    result = await ReadFileTool().execute({"path": "binary.bin"}, ctx)
    assert not result.ok
    assert result.error


@pytest.mark.asyncio
async def test_grep_invalid_regex_returns_error(tmp_path):
    ctx = ToolContext(workspace=str(tmp_path))
    result = await GrepTool().execute({"pattern": "["}, ctx)
    assert not result.ok
    assert "invalid regex" in result.error


@pytest.mark.asyncio
async def test_list_missing_dir_returns_error(tmp_path):
    ctx = ToolContext(workspace=str(tmp_path))
    result = await ListDirTool().execute({"path": "missing"}, ctx)
    assert not result.ok
    assert result.error


@pytest.mark.asyncio
async def test_list_outside_returns_error(tmp_path):
    ctx = ToolContext(workspace=str(tmp_path))
    result = await ListDirTool().execute({"path": "../outside"}, ctx)
    assert not result.ok
    assert "outside workspace" in result.error


@pytest.mark.asyncio
async def test_write_to_directory_returns_error(tmp_path):
    ctx = ToolContext(workspace=str(tmp_path))
    result = await WriteFileTool().execute({"path": ".", "content": "x"}, ctx)
    assert not result.ok
    assert result.error


import json
import subprocess

import pytest

from kl_server.tools.base import ToolContext
from kl_server.tools.builtin import register_builtin_tools
from kl_server.tools.builtin.filesystem import DeleteFileTool
from kl_server.tools.builtin.git import GitCommitTool, GitStatusTool
from kl_server.tools.builtin.patch import ApplyPatchTool
from kl_server.tools.builtin.shell import RunCommandTool
from kl_server.tools.builtin.task import TaskManageTool
from kl_server.tools.builtin.validation import RunTestsTool
from kl_server.tools.registry import ToolRegistry


@pytest.mark.asyncio
async def test_delete_file(tmp_path):
    ctx = ToolContext(workspace=str(tmp_path))
    (tmp_path / "a.txt").write_text("x", encoding="utf-8")
    result = await DeleteFileTool().execute({"path": "a.txt"}, ctx)
    assert result.ok is True
    assert not (tmp_path / "a.txt").exists()


@pytest.mark.asyncio
async def test_delete_file_outside_workspace(tmp_path):
    outside_file = tmp_path.parent / f"outside-{tmp_path.name}.txt"
    outside_file.write_text("x", encoding="utf-8")
    ctx = ToolContext(workspace=str(tmp_path))
    result = await DeleteFileTool().execute({"path": "../" + outside_file.name}, ctx)
    assert result.ok is False
    assert outside_file.exists()


@pytest.mark.asyncio
async def test_run_command_returns_structured_output(tmp_path):
    ctx = ToolContext(workspace=str(tmp_path))
    result = await RunCommandTool().execute({"command": "python -c \"import sys; sys.exit(3)\""}, ctx)
    payload = json.loads(result.output)
    assert payload["exit_code"] == 3
    assert payload["truncated"] is False


@pytest.mark.asyncio
async def test_apply_patch_single_hunk(tmp_path):
    ctx = ToolContext(workspace=str(tmp_path))
    (tmp_path / "a.txt").write_text("one\ntwo\n", encoding="utf-8")
    diff = "--- a.txt\n+++ b.txt\n@@ -1,2 +1,2 @@\n-one\n+one!\n two\n"
    result = await ApplyPatchTool().execute({"patch": diff}, ctx)
    assert (tmp_path / "a.txt").read_text(encoding="utf-8") == "one!\ntwo\n"


@pytest.mark.asyncio
async def test_apply_patch_git_diff_prefix(tmp_path):
    ctx = ToolContext(workspace=str(tmp_path))
    (tmp_path / "a.txt").write_text("one\ntwo\n", encoding="utf-8")
    diff = "--- a/a.txt\n+++ b/a.txt\n@@ -1,2 +1,2 @@\n-one\n+one!\n two\n"
    result = await ApplyPatchTool().execute({"patch": diff}, ctx)
    assert result.ok is True
    assert (tmp_path / "a.txt").read_text(encoding="utf-8") == "one!\ntwo\n"


@pytest.mark.asyncio
async def test_apply_patch_mismatch_does_not_write(tmp_path):
    ctx = ToolContext(workspace=str(tmp_path))
    (tmp_path / "a.txt").write_text("one\n", encoding="utf-8")
    diff = "--- a.txt\n+++ b.txt\n@@ -1 +1 @@\n-wrong\n+one!\n"
    result = await ApplyPatchTool().execute({"patch": diff}, ctx)
    assert result.ok is False
    assert result.error
    assert (tmp_path / "a.txt").read_text(encoding="utf-8") == "one\n"


@pytest.mark.asyncio
async def test_apply_patch_rejects_multiple_files(tmp_path):
    ctx = ToolContext(workspace=str(tmp_path))
    diff = (
        "--- a.txt\n+++ b.txt\n@@ -1 +1 @@\n-one\n+one!\n"
        "--- b.txt\n+++ b.txt\n@@ -1 +1 @@\n-two\n+two!\n"
    )
    result = await ApplyPatchTool().execute({"patch": diff}, ctx)
    assert result.ok is False
    assert "multi" in result.error


@pytest.mark.asyncio
async def test_git_status_in_repo(tmp_path):
    ctx = ToolContext(workspace=str(tmp_path))
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=tmp_path)
    subprocess.run(["git", "config", "user.name", "t"], cwd=tmp_path)
    result = await GitStatusTool().execute({}, ctx)
    assert result.ok is True


@pytest.mark.asyncio
async def test_git_commit_requires_paths(tmp_path):
    ctx = ToolContext(workspace=str(tmp_path))
    result = await GitCommitTool().execute({"message": "commit"}, ctx)
    assert result.ok is False
    assert "paths" in result.error


@pytest.mark.asyncio
async def test_validation_tool_reports_failed_tests(tmp_path):
    ctx = ToolContext(workspace=str(tmp_path))
    (tmp_path / "test_x.py").write_text("def test_x(): assert False\n", encoding="utf-8")
    result = await RunTestsTool().execute({}, ctx)
    payload = json.loads(result.output)
    assert payload["exit_code"] != 0


@pytest.mark.asyncio
async def test_task_manage_crud(tmp_path):
    ctx = ToolContext(workspace=str(tmp_path))
    created = await TaskManageTool().execute({"action": "create", "title": "fix bug"}, ctx)
    listed = await TaskManageTool().execute({"action": "list"}, ctx)
    assert created.ok and '"fix bug"' in listed.output
    updated = await TaskManageTool().execute({"action": "update", "item_id": "1", "status": "done"}, ctx)
    listed_after = await TaskManageTool().execute({"action": "list"}, ctx)
    assert updated.ok and '"done"' in listed_after.output


@pytest.mark.asyncio
async def test_task_manage_delete(tmp_path):
    ctx = ToolContext(workspace=str(tmp_path))
    await TaskManageTool().execute({"action": "create", "title": "temp"}, ctx)
    deleted = await TaskManageTool().execute({"action": "delete", "item_id": "1"}, ctx)
    listed = await TaskManageTool().execute({"action": "list"}, ctx)
    assert deleted.ok is True
    assert '"temp"' not in listed.output
    second = await TaskManageTool().execute({"action": "create", "title": "second"}, ctx)
    assert "2" in second.output


def test_register_builtin_tools_catalog():
    registry = ToolRegistry()
    register_builtin_tools(registry)
    names = {item["name"] for item in registry.catalog()}
    assert names == {
        "list_dir",
        "read_file",
        "write_file",
        "delete_file",
        "grep",
        "glob",
        "apply_patch",
        "run_command",
        "git_status",
        "git_diff",
        "git_branch",
        "git_commit",
        "run_tests",
        "run_lint",
        "typecheck",
        "task_manage",
    }
