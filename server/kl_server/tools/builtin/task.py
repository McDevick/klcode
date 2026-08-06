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

    async def _load_state(self, ctx: ToolContext) -> dict:
        store = getattr(ctx, "state_store", None)
        if store is not None and hasattr(store, "get_state"):
            raw = await store.get_state(
                f"session:{ctx.session_id or ctx.task_id}",
                "subtasks",
            )
            if raw:
                try:
                    state = json.loads(raw)
                except json.JSONDecodeError:
                    state = {}
                return state if isinstance(state, dict) else {}
        return ctx.task_state

    async def _save_state(self, ctx: ToolContext, state: dict) -> None:
        store = getattr(ctx, "state_store", None)
        if store is not None and hasattr(store, "set_state"):
            await store.set_state(
                f"session:{ctx.session_id or ctx.task_id}",
                "subtasks",
                json.dumps(state, ensure_ascii=False),
            )

    async def execute(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        state = await self._load_state(ctx)
        subtasks = state.setdefault("subtasks", [])
        action = args["action"]
        if action == "create":
            next_id = state.get("next_id", 1)
            item = {"id": str(next_id), "title": args.get("title", ""), "status": "pending"}
            subtasks.append(item)
            state["next_id"] = next_id + 1
            await self._save_state(ctx, state)
            return ToolResult(ok=True, output=json.dumps(subtasks, ensure_ascii=False))
        if action == "update":
            for item in subtasks:
                if item["id"] == args.get("item_id"):
                    item["status"] = args.get("status", item["status"])
                    if args.get("title"):
                        item["title"] = args["title"]
                    await self._save_state(ctx, state)
                    return ToolResult(ok=True, output=json.dumps(subtasks, ensure_ascii=False))
            return ToolResult(ok=False, output="", error="item not found")
        if action == "delete":
            for item in subtasks:
                if item["id"] == args.get("item_id"):
                    subtasks.remove(item)
                    await self._save_state(ctx, state)
                    return ToolResult(ok=True, output=json.dumps(subtasks, ensure_ascii=False))
            return ToolResult(ok=False, output="", error="item not found")
        if action == "list":
            return ToolResult(ok=True, output=json.dumps(subtasks, ensure_ascii=False))
        return ToolResult(ok=False, output="", error=f"unknown action: {action}")
