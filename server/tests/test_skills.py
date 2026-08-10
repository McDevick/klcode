import logging
from pathlib import Path

import pytest

from kl_server.skills.loader import SkillLoader
from kl_server.tools.base import ToolContext
from kl_server.tools.builtin.skills import ReadSkillTool


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


def test_skill_loader_lists_skills_with_descriptions(tmp_path):
    skill_dir = tmp_path / "skills"
    (skill_dir / "alpha").mkdir(parents=True)
    (skill_dir / "alpha" / "SKILL.md").write_text(
        "# Alpha\nDo alpha things",
        encoding="utf-8",
    )
    (skill_dir / "zeta").mkdir(parents=True)
    (skill_dir / "zeta" / "SKILL.md").write_text(
        "---\ndescription: Do zeta things\n---\n# Zeta",
        encoding="utf-8",
    )

    loader = SkillLoader(str(skill_dir))

    assert loader.list() == [
        {"name": "alpha", "description": "Do alpha things"},
        {"name": "zeta", "description": "Do zeta things"},
    ]


def test_skill_loader_list_missing_root_returns_empty(tmp_path):
    loader = SkillLoader(str(tmp_path / "missing"))

    assert loader.list() == []


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

def test_skill_loader_index_includes_structured_metadata(tmp_path):
    skill_dir = tmp_path / "skills" / "leetcode"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\n"
        "name: leetcode\n"
        "description: 算法题解题流程\n"
        "keywords: [cpp, algorithm]\n"
        "when_to_use: 用户要求写算法题\n"
        "summary: 先分析再编码并测试\n"
        "---\n"
        "## Workflow\n"
        "do work\n"
        "## Examples\n"
        "example\n",
        encoding="utf-8",
    )

    loader = SkillLoader(str(tmp_path / "skills"))

    assert loader.index() == [
        {
            "name": "leetcode",
            "description": "算法题解题流程",
            "keywords": ["cpp", "algorithm"],
            "when_to_use": "用户要求写算法题",
            "summary": "先分析再编码并测试",
            "always_on": False,
            "sections": ["Workflow", "Examples"],
        }
    ]


def test_skill_loader_rank_uses_keywords_and_description(tmp_path):
    skill_dir = tmp_path / "skills"
    (skill_dir / "leetcode").mkdir(parents=True)
    (skill_dir / "leetcode" / "SKILL.md").write_text(
        "---\nkeywords: [cpp, algorithm]\ndescription: algorithm coding\n---\nFull",
        encoding="utf-8",
    )
    (skill_dir / "python").mkdir(parents=True)
    (skill_dir / "python" / "SKILL.md").write_text(
        "# Python\nPython scripting",
        encoding="utf-8",
    )

    loader = SkillLoader(str(skill_dir))

    assert [item["name"] for item in loader.rank("写一个 cpp algorithm 题")] == ["leetcode"]
    assert [item["name"] for item in loader.rank("python 脚本")] == ["python"]
    assert loader.rank("完全无关内容") == []


def test_skill_loader_context_for_task_contains_summary_not_full_body(tmp_path):
    skill_dir = tmp_path / "skills" / "leetcode"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\n"
        "name: leetcode\n"
        "description: 算法题解题流程\n"
        "keywords: [cpp]\n"
        "summary: 先分析再编码并测试\n"
        "---\n"
        "SECRET FULL BODY\n"
        "long instructions that should not be injected at L1\n",
        encoding="utf-8",
    )

    context = SkillLoader(str(tmp_path / "skills")).context_for_task("cpp 算法题")

    assert "[可用 Skills]" in context
    assert "[任务相关 Skill]" in context
    assert "先分析再编码并测试" in context
    assert "SECRET FULL BODY" not in context


def test_skill_loader_load_named_and_section(tmp_path):
    skill_dir = tmp_path / "skills" / "demo"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: demo\ndescription: demo skill\n---\n"
        "## Workflow\nworkflow body\n"
        "## Examples\nexample body\n",
        encoding="utf-8",
    )
    loader = SkillLoader(str(tmp_path / "skills"))

    assert "workflow body" in loader.load_named("demo")
    assert loader.load_section("demo", "Workflow") == "workflow body"
    assert "Examples" in loader.load_section("demo", "missing")


def test_skill_loader_always_on_skills_are_always_in_context(tmp_path):
    skill_dir = tmp_path / "skills" / "safety"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: safety\ndescription: safety rules\nsummary: always follow safety\n"
        "always_on: true\n---\nFull safety body\n",
        encoding="utf-8",
    )

    context = SkillLoader(str(tmp_path / "skills")).context_for_task("unrelated task")

    assert "[始终启用 Skill]" in context
    assert "always follow safety" in context


def test_skill_loader_invalid_frontmatter_falls_back_to_legacy(tmp_path):
    skill_dir = tmp_path / "skills" / "legacy"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\n: not valid yaml\n---\n# Legacy\nLegacy description",
        encoding="utf-8",
    )

    loader = SkillLoader(str(tmp_path / "skills"))

    assert loader.index()[0]["description"] == "Legacy description"
    assert loader.has("legacy") is True


@pytest.mark.asyncio
async def test_read_skill_tool_returns_full_section_and_errors(tmp_path):
    skill_dir = tmp_path / "skills" / "demo"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: demo\ndescription: demo skill\n---\n"
        "## Workflow\nworkflow body\n"
        "## Examples\nexample body\n",
        encoding="utf-8",
    )
    loader = SkillLoader(str(tmp_path / "skills"))
    tool = ReadSkillTool(loader)
    ctx = ToolContext(workspace=".")

    full = await tool.execute({"name": "demo"}, ctx)
    section = await tool.execute({"name": "demo", "section": "Workflow"}, ctx)
    missing = await tool.execute({"name": "nope"}, ctx)

    assert full.ok is True
    assert "workflow body" in full.output
    assert section.ok is True
    assert section.output == "workflow body"
    assert missing.ok is False
    assert "skill not found" in missing.error