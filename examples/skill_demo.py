"""Mock-LLM demo: skill progressive disclosure driven by AgentLoop."""

import asyncio
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _demo_import import ensure_kl_server_importable  # noqa: E402
ensure_kl_server_importable()

from kl_server.core.agent_loop import AgentLoop, LoopSettings  # noqa: E402
from kl_server.core.tool_executor import ToolExecutor  # noqa: E402
from kl_server.models.task import Session  # noqa: E402
from kl_server.providers.mock import MockProvider  # noqa: E402
from kl_server.skills.loader import SkillLoader  # noqa: E402
from kl_server.tools.builtin.skills import ReadSkillTool  # noqa: E402
from kl_server.tools.registry import ToolRegistry  # noqa: E402


SKILL_MARKDOWN = """---
name: leetcode
description: LeetCode/C++ 算法题解题流程
keywords: [leetcode, 算法, cpp]
when_to_use: 用户要求解决算法题时
summary: 先分析题目结构，再编码并用测试验证。
---

## Workflow

1. 分析输入、输出、约束和边界情况。
2. 设计 C++ 解法。
3. 编写并运行测试。

## Examples

two_sum.cpp
"""


async def run_demo(root: Path):
    skill_dir = root / "skills" / "leetcode"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(SKILL_MARKDOWN, encoding="utf-8")

    loader = SkillLoader(str(root / "skills"))
    registry = ToolRegistry()
    registry.register(ReadSkillTool(loader))
    provider = MockProvider(
        responses=[
            '{"tool":"read_skill","args":{"name":"leetcode"}}',
            "DONE",
        ]
    )
    loop = AgentLoop(
        provider=provider,
        tools=ToolExecutor(registry),
        settings=LoopSettings(max_iterations=3),
        skills=loader,
    )
    result = await loop.run(
        Session(id="demo-skill", workspace=str(root), name="skill-demo"),
        "用 cpp 写一道 leetcode 算法题",
    )

    tool_result = [
        message
        for message in provider.calls[1].messages
        if message.get("role") == "tool"
    ]
    print("skill context is injected through AgentLoop:")
    print("  [可用 Skills] + [任务相关 Skill]")
    print("mock LLM next action: read_skill(\"leetcode\")")
    print(f"tool result contains workflow: {'## Workflow' in tool_result[0]['content']}")
    return provider, result, loader


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="kl-skill-demo-") as tmp:
        provider, result, loader = asyncio.run(run_demo(Path(tmp)))

        assert result == "DONE"
        assert provider.calls[0].tools is not None
        assert any(
            tool["function"]["name"] == "read_skill"
            for tool in provider.calls[0].tools
        )
        assert "## Workflow" in provider.calls[1].messages[-1]["content"]
        assert loader.index()[0]["name"] == "leetcode"


if __name__ == "__main__":
    main()