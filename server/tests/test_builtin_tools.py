from pathlib import Path

import pytest
from kl_server.memory.store import MemoryStore
from kl_server.tools.base import ToolContext
from kl_server.tools.builtin.filesystem import EditFileTool, ListDirTool, ReadFileTool, WriteFileTool
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
async def test_grep_and_glob_ignore_common_dirs(tmp_path):
    (tmp_path / "a.txt").write_text("needle", encoding="utf-8")
    ignored = tmp_path / "node_modules"
    ignored.mkdir()
    (ignored / "ignored.txt").write_text("needle", encoding="utf-8")
    ctx = ToolContext(workspace=str(tmp_path))

    grep = await GrepTool().execute({"pattern": "needle", "path": "."}, ctx)
    glob = await GlobTool().execute({"pattern": "**/*.txt"}, ctx)

    assert "a.txt" in grep.output
    assert "node_modules" not in grep.output
    assert "a.txt" in glob.output
    assert "node_modules" not in glob.output


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
async def test_read_file_range_returns_requested_lines(tmp_path):
    (tmp_path / "big.txt").write_text(
        "\n".join(f"line{i}" for i in range(1, 301)),
        encoding="utf-8",
    )
    ctx = ToolContext(workspace=str(tmp_path))
    result = await ReadFileTool().execute(
        {"path": "big.txt", "start_line": 2, "end_line": 4},
        ctx,
    )
    assert result.ok is True
    assert result.output == "line2\nline3\nline4"


@pytest.mark.asyncio
async def test_read_file_range_rejects_over_200_lines(tmp_path):
    (tmp_path / "big.txt").write_text(
        "\n".join(f"line{i}" for i in range(1, 301)),
        encoding="utf-8",
    )
    ctx = ToolContext(workspace=str(tmp_path))
    result = await ReadFileTool().execute(
        {"path": "big.txt", "start_line": 1, "end_line": 250},
        ctx,
    )
    assert result.ok is False
    assert "exceeds 200" in result.error


@pytest.mark.asyncio
async def test_read_file_end_line_only_clamps_to_200(tmp_path):
    (tmp_path / "big.txt").write_text(
        "\n".join(f"line{i}" for i in range(1, 301)),
        encoding="utf-8",
    )
    ctx = ToolContext(workspace=str(tmp_path))
    result = await ReadFileTool().execute({"path": "big.txt", "end_line": 500}, ctx)
    assert result.ok is True
    assert result.output.startswith("line1")
    assert "line200" in result.output
    assert "line201" not in result.output


@pytest.mark.asyncio
async def test_edit_file_replaces_first_old_text_occurrence(tmp_path):
    path = tmp_path / "a.txt"
    path.write_text("aaa\nbbb\naaa\n", encoding="utf-8")
    ctx = ToolContext(workspace=str(tmp_path))

    result = await EditFileTool().execute(
        {"path": "a.txt", "old_text": "aaa", "new_text": "XXX"},
        ctx,
    )

    assert result.ok is True
    assert path.read_text(encoding="utf-8") == "XXX\nbbb\naaa\n"


@pytest.mark.asyncio
async def test_edit_file_old_text_missing_does_not_write(tmp_path):
    path = tmp_path / "a.txt"
    path.write_text("original\n", encoding="utf-8")
    ctx = ToolContext(workspace=str(tmp_path))

    result = await EditFileTool().execute(
        {"path": "a.txt", "old_text": "missing", "new_text": "changed"},
        ctx,
    )

    assert result.ok is False
    assert "not found" in result.error
    assert path.read_text(encoding="utf-8") == "original\n"


@pytest.mark.asyncio
async def test_edit_file_replaces_line_range(tmp_path):
    path = tmp_path / "a.txt"
    path.write_text("\n".join(f"line{i}" for i in range(1, 6)), encoding="utf-8")
    ctx = ToolContext(workspace=str(tmp_path))

    result = await EditFileTool().execute(
        {
            "path": "a.txt",
            "start_line": 2,
            "end_line": 3,
            "new_content": "new2\nnew3",
        },
        ctx,
    )

    assert result.ok is True
    assert path.read_text(encoding="utf-8") == "line1\nnew2\nnew3\nline4\nline5"


@pytest.mark.asyncio
async def test_edit_file_rejects_line_range_over_200(tmp_path):
    path = tmp_path / "a.txt"
    path.write_text("\n".join(f"line{i}" for i in range(1, 301)), encoding="utf-8")
    ctx = ToolContext(workspace=str(tmp_path))

    result = await EditFileTool().execute(
        {"path": "a.txt", "start_line": 1, "end_line": 250},
        ctx,
    )

    assert result.ok is False
    assert "exceeds 200" in result.error


@pytest.mark.asyncio
async def test_edit_file_rejects_outside_workspace(tmp_path):
    ctx = ToolContext(workspace=str(tmp_path))
    result = await EditFileTool().execute(
        {"path": "../outside.txt", "old_text": "a", "new_text": "b"},
        ctx,
    )
    assert result.ok is False
    assert "outside workspace" in result.error


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
async def test_apply_patch_rejects_incorrect_hunk_count(tmp_path):
    ctx = ToolContext(workspace=str(tmp_path))
    (tmp_path / "a.txt").write_text("one\ntwo\nthree\n", encoding="utf-8")
    diff = "--- a.txt\n+++ b.txt\n@@ -1,3 +1,3 @@\n-one\n+one!\n"
    result = await ApplyPatchTool().execute({"patch": diff}, ctx)
    assert result.ok is False
    assert result.error
    assert (tmp_path / "a.txt").read_text(encoding="utf-8") == "one\ntwo\nthree\n"


@pytest.mark.asyncio
async def test_apply_patch_preserves_header_like_content_lines(tmp_path):
    ctx = ToolContext(workspace=str(tmp_path))
    (tmp_path / "a.txt").write_text("start\n---\nend\n", encoding="utf-8")
    diff = "--- a.txt\n+++ b.txt\n@@ -1,3 +1,3 @@\n start\n----\n++++\n end\n"
    result = await ApplyPatchTool().execute({"patch": diff}, ctx)
    assert result.ok is True
    assert (tmp_path / "a.txt").read_text(encoding="utf-8") == "start\n+++\nend\n"


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
async def test_apply_patch_rejects_path_not_matching_header(tmp_path):
    ctx = ToolContext(workspace=str(tmp_path))
    (tmp_path / "a.txt").write_text("one\n", encoding="utf-8")
    (tmp_path / "b.txt").write_text("unchanged\n", encoding="utf-8")
    diff = "--- a.txt\n+++ b.txt\n@@ -1 +1 @@\n-one\n+one!\n"

    result = await ApplyPatchTool().execute({"path": "b.txt", "patch": diff}, ctx)

    assert result.ok is False
    assert "path does not match" in result.error
    assert (tmp_path / "b.txt").read_text(encoding="utf-8") == "unchanged\n"


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
async def test_git_commit_rejects_empty_message(tmp_path):
    ctx = ToolContext(workspace=str(tmp_path))
    result = await GitCommitTool().execute({"message": "   ", "paths": ["a.txt"]}, ctx)
    assert result.ok is False
    assert "message is required" in result.error


@pytest.mark.asyncio
async def test_git_commit_rejects_path_outside_workspace(tmp_path):
    workspace = tmp_path / "sub"
    workspace.mkdir()
    (tmp_path / "outside.txt").write_text("outside", encoding="utf-8")
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=tmp_path)
    subprocess.run(["git", "config", "user.name", "t"], cwd=tmp_path)
    ctx = ToolContext(workspace=str(workspace))
    result = await GitCommitTool().execute({"message": "commit", "paths": ["../outside.txt"]}, ctx)
    assert result.ok is False
    assert "outside workspace" in result.error
    status = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    assert "A  outside.txt" not in status


@pytest.mark.asyncio
async def test_git_commit_only_requested_paths(tmp_path):
    workspace = tmp_path / "sub"
    workspace.mkdir()
    (tmp_path / "outside.txt").write_text("outside", encoding="utf-8")
    (workspace / "inside.txt").write_text("inside", encoding="utf-8")
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=tmp_path)
    subprocess.run(["git", "config", "user.name", "t"], cwd=tmp_path)
    subprocess.run(["git", "add", "outside.txt"], cwd=tmp_path, check=True)
    ctx = ToolContext(workspace=str(workspace))
    result = await GitCommitTool().execute({"message": "only inside", "paths": ["inside.txt"]}, ctx)
    assert result.ok is True
    files = subprocess.run(
        ["git", "show", "--name-only", "--format=", "HEAD"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    assert "sub/inside.txt" in files
    assert "outside.txt" not in files


@pytest.mark.asyncio
async def test_git_commit_rejects_pathspec_magic(tmp_path):
    workspace = tmp_path / "sub"
    workspace.mkdir()
    (tmp_path / "outside.txt").write_text("outside", encoding="utf-8")
    (workspace / "inside.txt").write_text("inside", encoding="utf-8")
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    ctx = ToolContext(workspace=str(workspace))
    result = await GitCommitTool().execute({"message": "no magic", "paths": [":(top)outside.txt"]}, ctx)
    assert result.ok is False
    assert "pathspec magic" in result.error


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
    assert created.ok
    assert '"fix bug"' in created.output
    assert '"fix bug"' in listed.output
    updated = await TaskManageTool().execute({"action": "update", "item_id": "1", "status": "done"}, ctx)
    listed_after = await TaskManageTool().execute({"action": "list"}, ctx)
    assert updated.ok
    updated_payload = json.loads(updated.output)
    assert updated_payload[0]["status"] == "done"
    assert '"done"' in listed_after.output


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


@pytest.mark.asyncio
async def test_task_manage_state_is_scoped_to_session(tmp_path):
    store = MemoryStore(tmp_path / "memory.db")
    await store.connect()
    try:
        first = ToolContext(
            workspace=str(tmp_path),
            task_id="t1",
            session_id="s1",
            state_store=store,
        )
        created = await TaskManageTool().execute(
            {"action": "create", "title": "fix bug"},
            first,
        )
        assert created.ok is True

        second_call = ToolContext(
            workspace=str(tmp_path),
            task_id="t2",
            session_id="s1",
            state_store=store,
        )
        listed = await TaskManageTool().execute({"action": "list"}, second_call)
        assert '"fix bug"' in listed.output

        other_session = ToolContext(
            workspace=str(tmp_path),
            task_id="t1",
            session_id="s2",
            state_store=store,
        )
        other_listed = await TaskManageTool().execute({"action": "list"}, other_session)
        assert '"fix bug"' not in other_listed.output
    finally:
        await store.close()


def test_register_builtin_tools_catalog():
    registry = ToolRegistry()
    register_builtin_tools(registry)
    names = {item["name"] for item in registry.catalog()}
    assert names == {
        "list_dir",
        "read_file",
        "edit_file",
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
