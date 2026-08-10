from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

_FRONTMATTER_RE = re.compile(r"\A\s*---\s*\n(.*?)\n---\s*\n?", re.DOTALL)
_SECTION_RE = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)
_WORD_RE = re.compile(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]+")

_MAX_INDEX_SKILLS = 30
_MAX_L1_SKILLS = 5


def _clean_text(value: Any, limit: int = 200) -> str:
    if not isinstance(value, str):
        value = str(value) if value is not None else ""
    return " ".join(value.split())[:limit]


def _legacy_description(markdown: str) -> str:
    """Return a short user-facing description from a legacy SKILL.md."""
    lines = markdown.splitlines()
    if lines and lines[0].strip() == "---":
        for index, line in enumerate(lines[1:], start=1):
            if line.strip() == "---":
                lines = lines[index + 1:]
                break
    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and not stripped.startswith("---"):
            return stripped[:200]
    return ""


def _split_frontmatter(markdown: str) -> tuple[dict, str]:
    match = _FRONTMATTER_RE.match(markdown)
    if not match:
        return {}, markdown
    try:
        data = yaml.safe_load(match.group(1)) or {}
    except Exception:
        return {}, markdown
    if not isinstance(data, dict):
        return {}, markdown
    return data, markdown[match.end():]


def _keyword_list(value: Any, fallback: str) -> list[str]:
    if isinstance(value, list):
        keywords = [str(item).strip()[:80] for item in value if str(item).strip()]
        if keywords:
            return keywords
    if isinstance(value, str) and value.strip():
        return [
            item.strip()[:80]
            for item in re.split(r"[,，;；\s]+", value)
            if item.strip()
        ]
    return [fallback]


def _sections(body: str) -> list[str]:
    seen: list[str] = []
    for match in _SECTION_RE.finditer(body):
        title = match.group(1).strip()
        if title and title not in seen:
            seen.append(title)
    return seen


class SkillLoader:
    """Load SKILL.md documents and expose progressive disclosure metadata."""

    def __init__(self, root: str):
        self.root = Path(root)

    def _iter_skill_docs(self):
        if not self.root.is_dir():
            logger.warning("Failed to iterate skill root %s: not a directory", self.root)
            return
        try:
            skill_dirs = sorted(self.root.iterdir(), key=lambda path: path.name)
        except OSError as exc:
            logger.warning("Failed to iterate skill root %s: %s", self.root, exc)
            return
        for skill_dir in skill_dirs:
            markdown = skill_dir / "SKILL.md"
            if not skill_dir.is_dir() or not markdown.is_file():
                continue
            try:
                yield skill_dir.name, markdown, markdown.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError) as exc:
                logger.warning("Failed to read skill document %s: %s", markdown, exc)

    def _parse_skill(self, name: str, markdown: str) -> dict[str, Any]:
        data, body = _split_frontmatter(markdown)
        meta_name = _clean_text(data.get("name"), 120) or name
        description = (
            _clean_text(data.get("description"), 200) or _legacy_description(markdown)
        )
        keywords = _keyword_list(data.get("keywords"), meta_name)
        return {
            "name": meta_name,
            "description": description,
            "keywords": keywords,
            "when_to_use": _clean_text(data.get("when_to_use"), 300),
            "summary": _clean_text(data.get("summary"), 500) or description,
            "always_on": bool(data.get("always_on", False)),
            "sections": _sections(body),
        }

    def _skill_records(self) -> list[dict[str, Any]]:
        records = []
        for name, path, text in self._iter_skill_docs():
            records.append(
                {
                    "meta": self._parse_skill(name, text),
                    "path": path,
                    "text": text,
                }
            )
        return sorted(records, key=lambda record: record["meta"]["name"].lower())

    def _find_skill(self, name: str):
        normalized = (name or "").strip().lower()
        if not normalized:
            return None
        for record in self._skill_records():
            meta_name = record["meta"]["name"].lower()
            directory_name = record["path"].stem.lower()
            if meta_name == normalized or directory_name == normalized:
                return record
        return None

    def index(self) -> list[dict[str, Any]]:
        return [dict(record["meta"]) for record in self._skill_records()]

    def list(self) -> list[dict[str, str]]:
        """Legacy-friendly two-field listing used by older consumers."""
        return [
            {"name": record["meta"]["name"], "description": record["meta"]["description"]}
            for record in self._skill_records()
        ]

    def load(self, keywords: list[str]) -> str:
        normalized_keywords = [keyword.strip() for keyword in keywords if keyword.strip()]
        if not normalized_keywords:
            return ""
        docs = []
        for record in self._skill_records():
            meta_name = record["meta"]["name"].lower()
            directory_name = record["path"].stem.lower()
            if any(
                meta_name in keyword.lower() or directory_name in keyword.lower()
                for keyword in normalized_keywords
            ):
                docs.append(record["text"])
        return "\n\n".join(docs)

    def load_named(self, name: str) -> str:
        record = self._find_skill(name)
        return record["text"] if record is not None else ""

    def load_section(self, name: str, section: str) -> str:
        record = self._find_skill(name)
        if record is None:
            return ""
        _, body = _split_frontmatter(record["text"])
        matches = list(_SECTION_RE.finditer(body))
        if not matches:
            return f"Skill '{name}' has no sections."
        wanted = section.strip().lower()
        for index, match in enumerate(matches):
            title = match.group(1).strip()
            if title.lower() == wanted:
                start = match.end()
                end = matches[index + 1].start() if index + 1 < len(matches) else len(body)
                return body[start:end].strip()
        available = ", ".join(match.group(1).strip() for match in matches)
        return f"Skill '{name}' section not found. Available sections: {available}"

    def has(self, name: str) -> bool:
        return self._find_skill(name) is not None

    def rank(self, task: str, limit: int = _MAX_L1_SKILLS) -> list[dict[str, Any]]:
        if not task:
            return []
        limit = max(0, int(limit))
        task_lower = task.lower()
        scored = []
        for record in self._skill_records():
            meta = record["meta"]
            score = 0
            if meta["name"].lower() and meta["name"].lower() in task_lower:
                score += 100
            for keyword in meta["keywords"]:
                if keyword.lower() and keyword.lower() in task_lower:
                    score += 20
            for field in ("description", "when_to_use", "summary"):
                for token in _WORD_RE.findall(meta[field].lower()):
                    if len(token) >= 2 and token in task_lower:
                        score += 2
            if score:
                scored.append((score, meta["name"].lower(), meta))
        scored.sort(key=lambda item: (-item[0], item[1]))
        return [item[2] for item in scored[:limit]]

    def context_for_task(self, task: str, limit: int = _MAX_L1_SKILLS) -> str:
        all_skills = self.index()
        if not all_skills:
            return ""
        limit = max(0, int(limit))
        always_on = [meta for meta in all_skills if meta["always_on"]]
        ranked = [
            meta
            for meta in self.rank(task, limit=max(0, limit - len(always_on)))
            if not meta["always_on"]
        ]
        lines = ["[可用 Skills]"]
        for meta in all_skills[:_MAX_INDEX_SKILLS]:
            lines.append(f"- {meta['name']}: {meta['description']}")
            triggers = ", ".join(meta["keywords"][:6])
            if triggers:
                lines.append(f"  触发: {triggers}")
        if always_on:
            lines.append("")
            lines.append("[始终启用 Skill]")
            for meta in always_on:
                lines.append(f"- {meta['name']}: {meta['summary'] or meta['description']}")
        if ranked:
            lines.append("")
            lines.append("[任务相关 Skill]")
            for meta in ranked:
                lines.append(f"- {meta['name']}: {meta['summary'] or meta['description']}")
                if meta["when_to_use"]:
                    lines.append(f"  适用: {meta['when_to_use']}")
        lines.append("")
        lines.append("如果某个 Skill 适用，先调用 read_skill(name) 读取完整说明，再按其中流程执行。")
        return "\n".join(lines)