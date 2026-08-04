"""Token-budgeted context assembly for the agent loop."""

import logging
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass

from kl_server.providers.base import ProviderRequest

logger = logging.getLogger(__name__)


class LLMSummarizer:
    def __init__(self, provider, model: str):
        self.provider = provider
        self.model = model

    async def summarize(self, segments: list[str], task_id: str) -> str:
        numbered_segments = "\n".join(
            f"{index}. {segment}" for index, segment in enumerate(segments, start=1)
        )
        prompt = (
            "Summarize segments for task "
            f"{task_id} with goals, results, failures, and open items:\n"
            f"{numbered_segments}"
        )
        request = ProviderRequest(
            messages=[{"role": "user", "content": prompt}],
            model=self.model,
        )
        try:
            response = await self.provider.complete(request)
        except Exception:
            logger.warning("LLM summarization failed for task %s", task_id, exc_info=True)
            raise
        return response.text


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
        summary_limit: int = 16,
    ):
        if summary_limit <= 0:
            raise ValueError("summary_limit must be positive")
        self.max_tokens = max_tokens
        self.token_estimator = token_estimator or self._default_token_estimate
        self.summarizer = None
        self.summary_limit = summary_limit
        self._summary_state: OrderedDict[str, tuple[int, str]] = OrderedDict()

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
        tool_catalog_text = self._format_tool_catalog(tool_catalog)
        base_sections = [rules]
        if tool_catalog_text:
            base_sections.append(tool_catalog_text)
        if skills:
            base_sections.append(skills)
        if memory:
            base_sections.append(memory[-1])

        budget = max(0, self.max_tokens)
        if history:
            all_sections = base_sections + list(history)
            if self._estimate("\n\n".join(all_sections)) <= budget:
                text, used_tokens = self._fit_to_budget(all_sections)
                return AssembledContext(text=text, used_tokens=used_tokens)

        summary = ""
        if self.summarizer and len(history) > 1:
            old_segments = history[:-1]
            state = self._read_summary_state(task_id)
            if state is not None:
                last_count, summary = state
                if len(old_segments) < last_count:
                    try:
                        summary = await self.summarizer.summarize(old_segments, task_id)
                        self._write_summary_state(task_id, len(old_segments), summary)
                    except Exception:
                        summary = ""
                elif len(old_segments) > last_count:
                    new_segments = old_segments[last_count:]
                    try:
                        summary = await self.summarizer.summarize(
                            [f"Previous summary: {summary}"] + new_segments,
                            task_id,
                        )
                        self._write_summary_state(task_id, len(old_segments), summary)
                    except Exception:
                        pass
            else:
                try:
                    summary = await self.summarizer.summarize(old_segments, task_id)
                    self._write_summary_state(task_id, len(old_segments), summary)
                except Exception:
                    summary = ""

        sections = list(base_sections)
        if history:
            sections.append(history[-1])
        if summary:
            sections.append(summary)

        text, used_tokens = self._fit_to_budget(sections)
        return AssembledContext(text=text, used_tokens=used_tokens)

    def _read_summary_state(self, task_id: str) -> tuple[int, str] | None:
        if task_id not in self._summary_state:
            return None
        self._summary_state.move_to_end(task_id)
        return self._summary_state[task_id]

    def _write_summary_state(self, task_id: str, count: int, summary: str) -> None:
        self._summary_state[task_id] = (count, summary)
        self._summary_state.move_to_end(task_id)
        while len(self._summary_state) > self.summary_limit:
            self._summary_state.popitem(last=False)

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
