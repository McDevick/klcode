import hashlib
import json
import logging
from collections import OrderedDict
from typing import Any

from kl_server.core.feedback import classify_command_result
from kl_server.core.tool_categories import COMMAND_TOOLS
from kl_server.models.action import ToolResult

logger = logging.getLogger(__name__)

_FILE_TOOLS = {"read_file"}
_SEARCH_TOOLS = {"grep", "glob"}
_INTERESTING_MARKERS = (
    "failed",
    "assert",
    "error",
    "exception",
    "lint",
    "warning",
)


def _lines(text: str) -> list[str]:
    return text.splitlines()


def _take(lines: list[str], limit: int) -> list[str]:
    return lines[:limit]


def _clip(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - len("\n...[summary truncated]")] + "\n...[summary truncated]"


class OutputSummarizer:
    """Summarize long tool outputs before they enter model history.

    Layer 1 uses deterministic extractors for known builtin tools.
    Layer 2 optionally asks an LLM to summarize unknown or very long outputs.
    """

    def __init__(
        self,
        llm_summarizer=None,
        deterministic_limit: int = 20_000,
        llm_threshold: int = 8_000,
        max_summary_chars: int = 4_000,
        cache_size: int = 64,
    ):
        self.llm_summarizer = llm_summarizer
        self.deterministic_limit = deterministic_limit
        self.llm_threshold = llm_threshold
        self.max_summary_chars = max_summary_chars
        self._cache: OrderedDict[str, str] = OrderedDict()
        self._cache_size = cache_size

    def _cache_key(self, tool: str, args: dict, output: str) -> str:
        payload = json.dumps(args, sort_keys=True, ensure_ascii=False, default=str)
        return hashlib.sha256(f"{tool}\n{payload}\n{output}".encode("utf-8")).hexdigest()

    def _cache_get(self, key: str) -> str | None:
        value = self._cache.get(key)
        if value is not None:
            self._cache.move_to_end(key)
        return value

    def _cache_set(self, key: str, value: str) -> None:
        self._cache[key] = value
        self._cache.move_to_end(key)
        while len(self._cache) > self._cache_size:
            self._cache.popitem(last=False)

    async def summarize(
        self,
        tool: str,
        args: dict[str, Any],
        result: ToolResult,
        task_id: str = "",
    ) -> str:
        if not result.ok:
            error = result.error or "tool failed with no error message"
            return _clip(error, self.max_summary_chars)
        raw = result.output or ""
        if not raw:
            return ""

        cache_key = self._cache_key(tool, args, raw)
        cached = self._cache_get(cache_key)
        if cached is not None:
            return cached

        summary = self._deterministic_summary(tool, args, raw)
        needs_llm = summary is None or len(summary) > self.llm_threshold
        if (
            len(raw) > self.llm_threshold
            and needs_llm
            and self.llm_summarizer is not None
        ):
            summarize_output = getattr(self.llm_summarizer, "summarize_output", None)
            if summarize_output is not None:
                try:
                    llm_summary = await summarize_output(raw, task_id)
                    if llm_summary and llm_summary.strip():
                        summary = llm_summary
                except Exception as exc:
                    logger.warning(
                        "LLM tool output summary failed for %s: %s",
                        tool,
                        exc,
                    )

        if summary is None:
            summary = self._head_tail(raw)
        summary = _clip(summary.strip() or raw, self.max_summary_chars)
        self._cache_set(cache_key, summary)
        return summary

    def _deterministic_summary(
        self,
        tool: str,
        args: dict[str, Any],
        output: str,
    ) -> str | None:
        if tool in COMMAND_TOOLS:
            return self._summarize_command(tool, output)
        if tool in _FILE_TOOLS:
            return self._summarize_file(args, output)
        if tool in _SEARCH_TOOLS:
            return self._summarize_search(args, output)
        if len(output) > self.llm_threshold:
            return None
        if len(output) > self.max_summary_chars:
            return self._head_tail(output)
        return output

    def _summarize_command(self, tool: str, output: str) -> str | None:
        try:
            payload = json.loads(output)
        except json.JSONDecodeError:
            return None if len(output) > self.llm_threshold else self._head_tail(output)
        if not isinstance(payload, dict) or not isinstance(payload.get("exit_code"), int):
            return None if len(output) > self.llm_threshold else self._head_tail(output)

        exit_code = payload["exit_code"]
        stdout = str(payload.get("stdout", ""))
        stderr = str(payload.get("stderr", ""))
        truncated = bool(payload.get("truncated"))
        status = classify_command_result(exit_code, stdout, stderr, tool).category.value
        marker = "\ntruncated: true" if truncated else ""
        if exit_code == 0:
            tail = "\n".join(_take(_lines(stdout)[-20:], 20))
            tail = _clip(tail, 2000)
            return f"exit_code: 0\nstatus: success\nstdout:\n{tail}{marker}"

        interesting = [
            line
            for line in _lines(f"{stdout}\n{stderr}")
            if any(marker.lower() in line.lower() for marker in _INTERESTING_MARKERS)
        ]
        body_lines = _take(interesting[-25:], 25) or _take(_lines(stderr)[-25:], 25)
        body = _clip("\n".join(body_lines), 2000)
        return f"exit_code: {exit_code}\nstatus: {status}\noutput_tail:\n{body}{marker}"

    def _summarize_file(self, args: dict[str, Any], output: str) -> str:
        lines = _lines(output)
        if len(lines) <= 40 and len(output) <= self.max_summary_chars:
            return output
        head = "\n".join(_take(lines, 20))
        tail = "\n".join(_take(lines[-20:], 20))
        return (
            f"path: {args.get('path', '')}\n"
            f"lines: {len(lines)}\n"
            f"head:\n{head}\n\n"
            f"tail:\n{tail}"
        )

    def _summarize_search(self, args: dict[str, Any], output: str) -> str:
        items = _lines(output)
        if len(items) <= 20 and len(output) <= self.max_summary_chars:
            return output
        first = "\n".join(_take(items, 15))
        last = "\n".join(_take(items[-5:], 5))
        return (
            f"pattern: {args.get('pattern', '')}\n"
            f"matches: {len(items)}\n"
            f"first:\n{first}\n\n"
            f"last:\n{last}"
        )

    def _head_tail(self, output: str) -> str:
        lines = _lines(output)
        head = "\n".join(_take(lines, 20))
        tail = "\n".join(_take(lines[-20:], 20))
        return f"truncated: true\nhead:\n{head}\n\ntail:\n{tail}"
