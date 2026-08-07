import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def _skill_description(markdown: str) -> str:
    """Return a short user-facing description from SKILL.md."""
    lines = markdown.splitlines()
    if lines and lines[0].strip() == "---":
        end_index = next(
            (index for index, line in enumerate(lines[1:], start=1) if line.strip() == "---"),
            None,
        )
        if end_index is not None:
            for line in lines[1:end_index]:
                if line.lower().startswith("description:"):
                    return line.split(":", 1)[1].strip()[:200]
            lines = lines[end_index + 1 :]
    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and not stripped.startswith("---"):
            return stripped[:200]
    return ""


class SkillLoader:
    """Load SKILL.md documents from keyword-matched skill directories."""

    def __init__(self, root: str):
        self.root = Path(root)

    def load(self, keywords: list[str]) -> str:
        normalized_keywords = [keyword.strip() for keyword in keywords if keyword.strip()]
        if not normalized_keywords:
            return ""

        if not self.root.is_dir():
            logger.warning("Failed to iterate skill root %s: not a directory", self.root)
            return ""

        try:
            skill_dirs = sorted(self.root.iterdir(), key=lambda path: path.name)
        except OSError as exc:
            logger.warning("Failed to iterate skill root %s: %s", self.root, exc)
            return ""

        docs = []
        for skill_dir in skill_dirs:
            markdown = skill_dir / "SKILL.md"
            if not skill_dir.is_dir() or not markdown.is_file():
                continue
            if not any(
                skill_dir.name.lower() in keyword.lower()
                for keyword in normalized_keywords
            ):
                continue
            try:
                docs.append(markdown.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError) as exc:
                logger.warning("Failed to read skill document %s: %s", markdown, exc)

        return "\n\n".join(docs)

    def list(self) -> list[dict[str, str]]:
        if not self.root.is_dir():
            logger.warning("Failed to iterate skill root %s: not a directory", self.root)
            return []

        try:
            skill_dirs = sorted(self.root.iterdir(), key=lambda path: path.name)
        except OSError as exc:
            logger.warning("Failed to iterate skill root %s: %s", self.root, exc)
            return []

        skills: list[dict[str, str]] = []
        for skill_dir in skill_dirs:
            markdown = skill_dir / "SKILL.md"
            if not skill_dir.is_dir() or not markdown.is_file():
                continue
            try:
                skills.append(
                    {
                        "name": skill_dir.name,
                        "description": _skill_description(markdown.read_text(encoding="utf-8")),
                    }
                )
            except (OSError, UnicodeDecodeError) as exc:
                logger.warning("Failed to read skill document %s: %s", markdown, exc)

        return skills
