"""Token-budgeted context assembly for the agent loop."""

import logging
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass

from kl_server.providers.base import ProviderRequest

logger = logging.getLogger(__name__)

# 注入上下文的记忆条数上限（最新 N 条）
MEMORY_LIMIT = 5


class LLMSummarizer:
    """Summarize old history with the current provider.

    ``provider`` and ``model`` may be either concrete values or zero-argument
    callables resolved at call time, so runtime provider/model switches are
    picked up by the next summary instead of staying pinned to boot values.
    """

    def __init__(self, provider, model: str | Callable[[], str]):
        self.provider = provider
        self.model = model

    def _resolve_provider(self):
        return self.provider() if callable(self.provider) else self.provider

    def _resolve_model(self) -> str:
        return self.model() if callable(self.model) else (self.model or "")

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
            model=self._resolve_model(),
        )
        try:
            response = await self._resolve_provider().complete(request)
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

    async def build(
        self,
        rules: str,
        memory: list[str],
        history: list[str],
        task_id: str = "t1",
        skills: str = "",
    ) -> AssembledContext:
        # 工具目录通过 OpenAI `tools` 请求参数传给模型（含 schema），
        # 不再占用上下文预算。
        base_sections = [rules]
        if skills:
            base_sections.append(skills)
        if memory:
            # 取最新若干条记忆（而非只有最后一条），按时间倒序自然排列
            base_sections.append("\n".join(memory[-MEMORY_LIMIT:]))

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
