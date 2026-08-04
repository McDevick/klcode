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
