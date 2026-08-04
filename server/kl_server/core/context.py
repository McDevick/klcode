"""Token-budgeted context assembly for the agent loop."""

from collections.abc import Callable
from dataclasses import dataclass


@dataclass
class AssembledContext:
    text: str
    used_tokens: int

    def contains_priority(self, text: str) -> bool:
        return text in self.text


class ContextAssembler:
    def __init__(
        self,
        max_tokens: int,
        token_estimator: Callable[[str], int] | None = None,
    ):
        self.max_tokens = max_tokens
        self.token_estimator = token_estimator or self._default_token_estimate
        self.summarizer = None

    @staticmethod
    def _default_token_estimate(text: str) -> int:
        return len(text) // 4

    @staticmethod
    def _format_tool_catalog(tool_catalog: list[dict]) -> str:
        if not tool_catalog:
            return ""
        lines = ["Tool catalog:"]
        for tool in tool_catalog:
            name = tool.get("name", "")
            description = tool.get("description", "")
            lines.append(f"- {name}: {description}")
        return "\n".join(lines)

    async def build(
        self,
        tool_catalog: list[dict],
        rules: str,
        memory: list[str],
        history: list[str],
        task_id: str = "t1",
        skills: str = "",
    ) -> AssembledContext:
        summary = ""
        if self.summarizer and len(history) > 2:
            try:
                summary = await self.summarizer.summarize(history[:-1], task_id)
            except Exception:
                summary = ""

        tool_catalog_text = self._format_tool_catalog(tool_catalog)
        sections = [rules]
        if tool_catalog_text:
            sections.append(tool_catalog_text)
        if skills:
            sections.append(skills)
        if memory:
            sections.append(memory[-1])
        if history:
            sections.append(history[-1])
        if summary:
            sections.append(summary)

        text, used_tokens = self._fit_to_budget(sections)
        return AssembledContext(text=text, used_tokens=used_tokens)

    def _fit_to_budget(self, sections: list[str]) -> tuple[str, int]:
        budget = max(0, self.max_tokens)
        while sections:
            text = "\n\n".join(sections)
            if self._estimate(text) <= budget:
                return text, self._estimate(text)
            if len(sections) == 1:
                return self._truncate_single(sections[0], budget)

            fixed_text = "\n\n".join(sections[:-1])
            if self._estimate(fixed_text) <= budget:
                truncated = self._truncate_section(fixed_text, sections[-1], budget)
                if truncated:
                    sections[-1] = truncated
                    text = "\n\n".join(sections)
                else:
                    sections.pop()
                    text = "\n\n".join(sections)
                return text, self._estimate(text)
            sections.pop()
        return "", self._estimate("")

    def _estimate(self, text: str) -> int:
        return self.token_estimator(text)

    def _truncate_single(self, section: str, budget: int) -> tuple[str, int]:
        lo, hi = 0, len(section)
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if self._estimate(section[:mid]) <= budget:
                lo = mid
            else:
                hi = mid - 1
        text = section[:lo]
        return text, self._estimate(text)

    def _truncate_section(self, fixed_text: str, section: str, budget: int) -> str:
        lo, hi = 0, len(section)
        while lo < hi:
            mid = (lo + hi + 1) // 2
            candidate = f"{fixed_text}\n\n{section[:mid]}"
            if self._estimate(candidate) <= budget:
                lo = mid
            else:
                hi = mid - 1
        return section[:lo]
