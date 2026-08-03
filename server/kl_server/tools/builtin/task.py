import json
from typing import Any

from kl_server.models.action import ToolResult
from kl_server.tools.base import Tool, ToolContext


class TaskManageTool(Tool):
    name = "task_manage"
    description = "Track the task's sub-task breakdown: create / update / list"
    schema = {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ["create", "update", "list"]},
            "title": {"type": "string"},
            "item_id": {"type": "string"},
            "status": {"type": "string"},
        },
        "required": ["action"],
    }

    async def execute(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        subtasks = ctx.task_state.setdefault("subtasks", [])
        action = args["action"]
        if action == "create":
            item = {"id": str(len(subtasks) + 1), "title": args.get("title", ""), "status": "pending"}
            subtasks.append(item)
            return ToolResult(ok=True, output=f"created {item['id']}")
        if action == "update":
            for item in subtasks:
                if item["id"] == args.get("item_id"):
                    item["status"] = args.get("status", item["status"])
                    if args.get("title"):
                        item["title"] = args["title"]
                    return ToolResult(ok=True, output=f"updated {item['id']}")
            return ToolResult(ok=False, output="", error="item not found")
        if action == "list":
            return ToolResult(ok=True, output=json.dumps(subtasks, ensure_ascii=False))
        return ToolResult(ok=False, output="", error=f"unknown action: {action}")
