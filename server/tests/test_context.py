import pytest

from kl_server.core.context import ContextAssembler


@pytest.mark.asyncio
async def test_context_keeps_priority_sections():
    assembler = ContextAssembler(max_tokens=100)
    result = await assembler.build(
        tool_catalog=[],
        rules="rules",
        memory=["m1", "m2"],
        history=["h1", "h2", "h3"],
    )
    assert result.contains_priority("rules")
    assert result.used_tokens <= 100


@pytest.mark.asyncio
async def test_context_keeps_latest_history_when_it_fits_budget():
    assembler = ContextAssembler(max_tokens=10)
    result = await assembler.build(
        tool_catalog=[],
        rules="rules",
        memory=["m1", "m2"],
        history=["old-" + "x" * 200, "old-" + "y" * 200, "latest"],
    )
    assert result.contains_priority("rules")
    assert result.contains_priority("m2")
    assert result.contains_priority("latest")
    assert result.used_tokens <= 10


@pytest.mark.asyncio
async def test_context_truncates_priority_sections_as_last_resort():
    assembler = ContextAssembler(max_tokens=4)
    result = await assembler.build(
        tool_catalog=[],
        rules="r" * 100,
        memory=["m" * 100],
        history=["h" * 100],
    )
    assert result.used_tokens <= 4
    assert result.text.startswith("r")


@pytest.mark.asyncio
async def test_context_includes_tool_catalog_after_rules():
    assembler = ContextAssembler(max_tokens=100)
    result = await assembler.build(
        tool_catalog=[{"name": "echo", "description": "Echoes input."}],
        rules="rules",
        memory=[],
        history=[],
    )
    assert result.text.index("rules") < result.text.index("Tool catalog:")
    assert result.contains_priority("- echo: Echoes input.")
    assert result.used_tokens <= 100


@pytest.mark.asyncio
async def test_latest_history_is_kept_over_lower_priority_summary():
    class FakeSummarizer:
        async def summarize(self, segments, task_id):
            return "S" * 200

    assembler = ContextAssembler(max_tokens=10, token_estimator=len)
    assembler.summarizer = FakeSummarizer()
    result = await assembler.build(
        tool_catalog=[],
        rules="r",
        memory=[],
        history=["old1", "old2", "latest"],
    )
    assert result.contains_priority("latest")
    assert "S" not in result.text
    assert result.used_tokens <= 10


@pytest.mark.asyncio
async def test_summarizer_failure_keeps_latest_history_once():
    class FailingSummarizer:
        async def summarize(self, segments, task_id):
            raise RuntimeError("summarizer failed")

    assembler = ContextAssembler(max_tokens=100)
    assembler.summarizer = FailingSummarizer()
    result = await assembler.build(
        tool_catalog=[],
        rules="rules",
        memory=[],
        history=["old1", "old2", "latest"],
    )
    assert result.text.count("latest") == 1


@pytest.mark.asyncio
async def test_context_uses_injected_token_estimator():
    assembler = ContextAssembler(max_tokens=10, token_estimator=len)
    result = await assembler.build(
        tool_catalog=[],
        rules="r" * 100,
        memory=["m" * 100],
        history=["h" * 100],
    )
    assert result.used_tokens == len(result.text)
    assert result.used_tokens <= 10


@pytest.mark.asyncio
async def test_empty_input_builds_empty_context():
    assembler = ContextAssembler(max_tokens=100)
    result = await assembler.build(
        tool_catalog=[],
        rules="",
        memory=[],
        history=[],
        skills="",
    )
    assert result.text == ""
    assert result.used_tokens == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("max_tokens", [0, -1])
async def test_non_positive_budget_is_deterministic(max_tokens):
    assembler = ContextAssembler(max_tokens=max_tokens)
    result = await assembler.build(
        tool_catalog=[{"name": "x", "description": "d"}],
        rules="r" * 100,
        memory=["m" * 100],
        history=["h" * 100],
    )
    assert result.used_tokens == len(result.text) // 4
    assert result.used_tokens <= 0
