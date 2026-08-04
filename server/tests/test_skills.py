import logging
from pathlib import Path

from kl_server.skills.loader import SkillLoader


def test_skill_loader_finds_by_keyword(tmp_path):
    skill_dir = tmp_path / "skills"
    (skill_dir / "python").mkdir(parents=True)
    (skill_dir / "python" / "SKILL.md").write_text("# Python\nUse pytest", encoding="utf-8")
    loader = SkillLoader(str(skill_dir))
    assert "pytest" in loader.load(["python"])


def test_skill_loader_matches_directory_name_in_task_text(tmp_path):
    skill_dir = tmp_path / "skills"
    (skill_dir / "python").mkdir(parents=True)
    (skill_dir / "python" / "SKILL.md").write_text("# Python\nUse pytest", encoding="utf-8")
    loader = SkillLoader(str(skill_dir))

    assert "pytest" in loader.load(["fix python code"])


def test_skill_loader_missing_root_returns_empty(tmp_path):
    loader = SkillLoader(str(tmp_path / "missing"))
    assert loader.load(["python"]) == ""


def test_skill_loader_rejects_non_directory_root(tmp_path, caplog):
    root = tmp_path / "skills.txt"
    root.write_text("not a directory", encoding="utf-8")

    loader = SkillLoader(str(root))

    with caplog.at_level(logging.WARNING, logger="kl_server.skills.loader"):
        result = loader.load(["python"])

    assert result == ""
    assert "Failed to iterate skill root" in caplog.text


def test_skill_loader_empty_keywords_load_nothing(tmp_path):
    skill_dir = tmp_path / "skills"
    (skill_dir / "python").mkdir(parents=True)
    (skill_dir / "python" / "SKILL.md").write_text("# Python", encoding="utf-8")

    loader = SkillLoader(str(skill_dir))

    assert loader.load([]) == ""
    assert loader.load([""]) == ""
    assert loader.load(["   "]) == ""


def test_skill_loader_only_loads_matching_dirs(tmp_path):
    skill_dir = tmp_path / "skills"
    for name in ("python", "typescript"):
        (skill_dir / name).mkdir(parents=True)
        (skill_dir / name / "SKILL.md").write_text(f"# {name}", encoding="utf-8")

    loader = SkillLoader(str(skill_dir))
    assert loader.load(["python"]) == "# python"


def test_skill_loader_skips_dirs_without_skill_md(tmp_path):
    skill_dir = tmp_path / "skills"
    (skill_dir / "python").mkdir(parents=True)

    loader = SkillLoader(str(skill_dir))
    assert loader.load(["python"]) == ""


def test_skill_loader_sorts_output(tmp_path):
    skill_dir = tmp_path / "skills"
    for name in ("zeta", "alpha"):
        (skill_dir / name).mkdir(parents=True)
        (skill_dir / name / "SKILL.md").write_text(f"# {name}", encoding="utf-8")

    loader = SkillLoader(str(skill_dir))
    assert loader.load(["alpha zeta"]) == "# alpha\n\n# zeta"


def test_skill_loader_skips_unreadable_document(tmp_path, monkeypatch, caplog):
    skill_dir = tmp_path / "skills"
    markdown = skill_dir / "python" / "SKILL.md"
    markdown.parent.mkdir(parents=True)
    markdown.write_text("# Python", encoding="utf-8")

    def fail_read(path, **kwargs):
        raise OSError("boom")

    monkeypatch.setattr(Path, "read_text", fail_read)
    loader = SkillLoader(str(skill_dir))

    with caplog.at_level(logging.WARNING, logger="kl_server.skills.loader"):
        result = loader.load(["python"])

    assert result == ""
    assert "Failed to read skill document" in caplog.text


def test_skill_loader_skips_invalid_utf8_document(tmp_path, caplog):
    skill_dir = tmp_path / "skills"
    markdown = skill_dir / "python" / "SKILL.md"
    markdown.parent.mkdir(parents=True)
    markdown.write_bytes(b"\xff\xfe")

    loader = SkillLoader(str(skill_dir))

    with caplog.at_level(logging.WARNING, logger="kl_server.skills.loader"):
        result = loader.load(["python"])

    assert result == ""
    assert "Failed to read skill document" in caplog.text
