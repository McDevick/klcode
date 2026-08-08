"""Token-budgeted context assembly for the agent loop."""

import logging
import re
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass

from kl_server.providers.base import ProviderRequest

logger = logging.getLogger(__name__)

# Phase 1：记忆按 kind 配额注入，tool_result/task 只写库不进上下文。
MEMORY_KIND_QUOTAS = {
    "user_note": 2,
    "feedback": 2,
    "context_summary": 1,
}
KEYWORD_MEMORY_LIMIT = 3
_MEMORY_TOKEN_RE = re.compile(r"[a-z0-9_]+|[\u4e00-\u9fff]+")
_MEMORY_STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "at",
    "for",
    "in",
    "is",
    "of",
    "on",
    "or",
    "the",
    "to",
    "with",
    "请",
    "帮我",
    "需要",
    "可以",
    "这个",
    "这些",
    "继续",
    "然后",
    "并且",
    "我们",
    "你们",
    "进行",
}
_MEMORY_CHAR_STOPWORDS = {
    "请",
    "我",
    "你",
    "这",
    "那",
}


def extract_memory_keywords(task: str, limit: int = 8) -> list[str]:
    """从任务描述提取稳定、可测试的关键词，不引入分词依赖。"""
    keywords: list[str] = []
    text = (task or "").lower()

    def add(token: str) -> None:
        nonlocal keywords
        if token in _MEMORY_STOPWORDS or token in keywords:
            return
        keywords.append(token)

    for match in _MEMORY_TOKEN_RE.finditer(text):
        token = match.group(0)
        if token.isascii():
            add(token)
            if len(keywords) >= limit:
                return keywords
            continue
        run = token
        for stopword in _MEMORY_STOPWORDS:
            if len(stopword) > 1 and all("\u4e00" <= ch <= "\u9fff" for ch in stopword):
                run = run.replace(stopword, "")
        for index in range(len(run) - 1):
            bigram = run[index : index + 2]
            if any(char in _MEMORY_CHAR_STOPWORDS for char in bigram):
                continue
            add(bigram)
            if len(keywords) >= limit:
                return keywords
    return keywords


async def select_memory_entries(
    memory,
    tags: list[str],
    task: str = "",
    keyword_limit: int = KEYWORD_MEMORY_LIMIT,
) -> list[str]:
    """按 kind 配额和任务关键词选择要注入上下文的记忆。"""
    if memory is None:
        return []
    selected: list[str] = []
    seen: set[str] = set()
    allowed_kinds = list(MEMORY_KIND_QUOTAS)

    for kind, limit in MEMORY_KIND_QUOTAS.items():
        entries = await memory.find(tags, kinds=[kind], limit=limit)
        for entry in entries:
            if entry not in seen:
                seen.add(entry)
                selected.append(entry)

    keywords = extract_memory_keywords(task)
    if keywords:
        entries = await memory.find(
            tags,
            kinds=allowed_kinds,
            keywords=keywords,
            limit=keyword_limit,
        )
        for entry in entries:
            if entry not in seen:
                seen.add(entry)
                selected.append(entry)
    return selected


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
            "You are compressing an agent session context.\n"
            f"Task: {task_id}\n\n"
            "Produce a concise structured summary with these sections:\n"
            "## Goals\n"
            "## Results\n"
            "## Failures\n"
            "## Open Items\n\n"
            "Rules:\n"
            "- Preserve exact file paths, commands, tool names, decisions, and pending work.\n"
            "- Do not invent facts or tool results.\n"
            "- Remove repeated or low-signal details.\n"
            "- Keep the summary under 1000 tokens when possible.\n"
            "- Use Chinese if the source segments are Chinese.\n\n"
            "Segments:\n"
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

    async def summarize_output(self, text: str, task_id: str = "") -> str:
        prompt = (
            "You are summarizing a single tool output for an autonomous coding agent.\n"
            f"Task: {task_id}\n\n"
            "Preserve exact file paths, line numbers, exit codes, commands, "
            "error messages, failure cases, and any facts needed to continue.\n"
            "Do not invent results.\n"
            "Keep the summary under 800 tokens when possible.\n"
            "Use Chinese if the source text is Chinese.\n\n"
            "Tool output:\n"
            f"{text}"
        )
        request = ProviderRequest(
            messages=[{"role": "user", "content": prompt}],
            model=self._resolve_model(),
        )
        try:
            response = await self._resolve_provider().complete(request)
        except Exception:
            logger.warning(
                "LLM tool output summarization failed for task %s",
                task_id,
                exc_info=True,
            )
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
            base_sections.append("\n".join(memory))

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

        if self.summarizer is None and len(history) > 1:
            logger.warning(
                "Dropping %d old history sections without summary: %s",
                len(history) - 1,
                str(history[0])[:200],
            )

        sections = list(base_sections)
        if history:
            sections.append(history[-1])
        if summary:
            sections.append(summary)

        text, used_tokens = self._fit_to_budget(sections)
        return AssembledContext(text=text, used_tokens=used_tokens)

    def estimate_tokens(self, text: str) -> int:
        return self._estimate(text)

    def should_compress(self, history: list[str]) -> bool:
        if not history:
            return False
        return self._estimate("\n\n".join(history)) > int(self.max_tokens * 0.8)

    async def compact_history(self, history: list[str], task_id: str) -> str:
        if not history or self.summarizer is None:
            return ""
        return await self.summarizer.summarize(history, task_id)

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
                    dropped = sections.pop()
                    logger.warning(
                        "Dropping context section due to budget (%d chars): %s",
                        len(dropped),
                        dropped[:200],
                    )
                    text = "\n\n".join(sections)
                return text, self._estimate(text)
            dropped = sections.pop()
            logger.warning(
                "Dropping context section due to budget (%d chars): %s",
                len(dropped),
                dropped[:200],
            )
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
        if len(text) < len(section):
            logger.warning(
                "Truncating context section from %d to %d chars",
                len(section),
                len(text),
            )
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
        result = section[:lo]
        if len(result) < len(section):
            logger.warning(
                "Truncating context section from %d to %d chars",
                len(section),
                len(result),
            )
        return result
