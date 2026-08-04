import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class SkillLoader:
    """Load SKILL.md documents from keyword-matched skill directories."""

    def __init__(self, root: str):
        self.root = Path(root)

    def load(self, keywords: list[str]) -> str:
        if not self.root.exists():
            return ""

        docs = []
        for skill_dir in sorted(self.root.iterdir(), key=lambda path: path.name):
            markdown = skill_dir / "SKILL.md"
            if not skill_dir.is_dir() or not markdown.is_file():
                continue
            if not any(keyword in skill_dir.name for keyword in keywords):
                continue
            try:
                docs.append(markdown.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError) as exc:
                logger.warning("Failed to read skill document %s: %s", markdown, exc)

        return "\n\n".join(docs)
