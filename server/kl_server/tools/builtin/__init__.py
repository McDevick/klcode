"""Built-in workspace tools."""

from kl_server.tools.registry import ToolRegistry

from .filesystem import DeleteFileTool, EditFileTool, ListDirTool, ReadFileTool, WriteFileTool
from .git import GitBranchTool, GitCommitTool, GitDiffTool, GitStatusTool
from .patch import ApplyPatchTool
from .search import GlobTool, GrepTool
from .shell import RunCommandTool
from .task import TaskManageTool
from .validation import RunLintTool, RunTestsTool, TypecheckTool


def register_builtin_tools(registry: ToolRegistry) -> None:
    """Register all built-in workspace tools on a tool registry."""
    tools = [
        ListDirTool(),
        ReadFileTool(),
        EditFileTool(),
        WriteFileTool(),
        DeleteFileTool(),
        GrepTool(),
        GlobTool(),
        ApplyPatchTool(),
        RunCommandTool(),
        GitStatusTool(),
        GitDiffTool(),
        GitBranchTool(),
        GitCommitTool(),
        RunTestsTool(),
        RunLintTool(),
        TypecheckTool(),
        TaskManageTool(),
    ]
    for tool in tools:
        registry.register(tool)
