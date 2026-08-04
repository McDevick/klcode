import logging
from pathlib import Path

logger = logging.getLogger(__name__)


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
            if not any(keyword in skill_dir.name for keyword in normalized_keywords):
                continue
            try:
                docs.append(markdown.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError) as exc:
                logger.warning("Failed to read skill document %s: %s", markdown, exc)

        return "\n\n".join(docs)
