import json
from typing import Any

from kl_server.models.action import ToolResult
from kl_server.tools.base import Tool, ToolContext


class TaskManageTool(Tool):
    name = "task_manage"
    description = "Track the task's sub-task breakdown: create / update / delete / list"
    schema = {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ["create", "update", "delete", "list"]},
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
            next_id = ctx.task_state.get("next_id", 1)
            item = {"id": str(next_id), "title": args.get("title", ""), "status": "pending"}
            subtasks.append(item)
            ctx.task_state["next_id"] = next_id + 1
            return ToolResult(ok=True, output=f"created {item['id']}")
        if action == "update":
            for item in subtasks:
                if item["id"] == args.get("item_id"):
                    item["status"] = args.get("status", item["status"])
                    if args.get("title"):
                        item["title"] = args["title"]
                    return ToolResult(ok=True, output=f"updated {item['id']}")
            return ToolResult(ok=False, output="", error="item not found")
        if action == "delete":
            for item in subtasks:
                if item["id"] == args.get("item_id"):
                    subtasks.remove(item)
                    return ToolResult(ok=True, output=f"deleted {item['id']}")
            return ToolResult(ok=False, output="", error="item not found")
        if action == "list":
            return ToolResult(ok=True, output=json.dumps(subtasks, ensure_ascii=False))
        return ToolResult(ok=False, output="", error=f"unknown action: {action}")
