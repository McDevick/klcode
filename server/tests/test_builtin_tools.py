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
