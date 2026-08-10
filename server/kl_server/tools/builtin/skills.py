from typing import Any

from kl_server.models.action import ToolResult
from kl_server.skills.loader import SkillLoader
from kl_server.tools.base import Tool, ToolContext
from kl_server.tools.registry import ToolRegistry


class ReadSkillTool(Tool):
    name = "read_skill"
    description = (
        "Read the full instructions of a skill. Use only after determining "
        "the skill is relevant; optionally pass a section for large skills."
    )
    schema = {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "section": {"type": "string"},
        },
        "required": ["name"],
    }
    permissions = ["skill"]
    sandbox = {"read_only": True}
    timeout = 10.0

    def __init__(self, loader: SkillLoader):
        self.loader = loader

    async def execute(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        name = str(args.get("name") or "").strip()
        if not self.loader.has(name):
            return ToolResult(ok=False, output="", error=f"skill not found: {name}")
        section = args.get("section")
        if isinstance(section, str) and section.strip():
            output = self.loader.load_section(name, section)
            return ToolResult(ok=True, output=output)
        output = self.loader.load_named(name)
        return ToolResult(ok=True, output=output)


def register_skill_tools(registry: ToolRegistry, loader: SkillLoader) -> None:
    registry.register(ReadSkillTool(loader))