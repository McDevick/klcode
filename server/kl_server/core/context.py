"""Token-budgeted context assembly for the agent loop."""

from dataclasses import dataclass


@dataclass
class AssembledContext:
    text: str
    used_tokens: int

    def contains_priority(self, text: str) -> bool:
        return text in self.text


class ContextAssembler:
    def __init__(self, max_tokens: int):
        self.max_tokens = max_tokens
        self.summarizer = None

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
                summary = history[-1]

        sections = [rules]
        if skills:
            sections.append(skills)
        if memory:
            sections.append(memory[-1])
        if summary:
            sections.append(summary)
        if history:
            sections.append(history[-1])

        text = "\n\n".join(sections)
        char_budget = max(0, self.max_tokens * 4)
        while text and len(text) > char_budget:
            if len(sections) == 1:
                text = text[:char_budget]
                break
            fixed_len = len("\n\n".join(sections[:-1]))
            remaining = char_budget - fixed_len - 2
            if remaining <= 0:
                sections.pop()
                text = "\n\n".join(sections)
            else:
                sections[-1] = sections[-1][:remaining]
                text = "\n\n".join(sections)
        return AssembledContext(text=text, used_tokens=max(1, len(text) // 4) if text else 0)
