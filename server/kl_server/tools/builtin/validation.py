from typing import Any

from kl_server.models.action import ToolResult
from kl_server.tools.base import Tool, ToolContext
from kl_server.tools.builtin.shell import RunCommandTool


class RunTestsTool(Tool):
    name = "run_tests"
    description = "Run the test suite"
    schema = {"type": "object", "properties": {"command": {"type": "string"}}}
    permissions = ["command", "validation"]
    sandbox = {"allow": [], "deny": []}
    timeout = 180.0

    async def execute(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        return await RunCommandTool().execute({"command": args.get("command", "pytest -q")}, ctx)


class RunLintTool(Tool):
    name = "run_lint"
    description = "Run the linter"
    schema = {"type": "object", "properties": {"command": {"type": "string"}}}
    permissions = ["command", "validation"]
    sandbox = {"allow": [], "deny": []}
    timeout = 120.0

    async def execute(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        return await RunCommandTool().execute({"command": args.get("command", "ruff check .")}, ctx)


class TypecheckTool(Tool):
    name = "typecheck"
    description = "Run the type checker"
    schema = {"type": "object", "properties": {"command": {"type": "string"}}}
    permissions = ["command", "validation"]
    sandbox = {"allow": [], "deny": []}
    timeout = 120.0

    async def execute(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        return await RunCommandTool().execute({"command": args.get("command", "mypy .")}, ctx)
