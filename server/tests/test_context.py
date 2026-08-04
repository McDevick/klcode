import pytest

from kl_server.core.context import ContextAssembler, LLMSummarizer
from kl_server.providers.mock import MockProvider


@pytest.mark.asyncio
async def test_summarizer_uses_provider_and_keeps_raw():
    provider = MockProvider(responses=["summary"])
    summarizer = LLMSummarizer(provider, model="mock-model")
    result = await summarizer.summarize(["old action", "old result"], "t1")
    assert result == "summary"


@pytest.mark.asyncio
async def test_summarizer_builds_provider_request():
    provider = MockProvider(responses=["summary"])
    summarizer = LLMSummarizer(provider, model="mock-model")
    segments = ["old action\nline2", "old result"]
    await summarizer.summarize(segments, "t1")

    assert len(provider.calls) == 1
    request = provider.calls[0]
    assert request.model == "mock-model"
    assert request.max_tokens == 2048
    content = request.messages[0]["content"]
    assert request.messages == [{"role": "user", "content": content}]
    assert "old action\nline2" in content
    assert "old result" in content
    assert "t1" in content


@pytest.mark.asyncio
async def test_assembler_uses_provider_summary_without_repeating_latest():
    provider = MockProvider(responses=["summary"])
    assembler = ContextAssembler(max_tokens=100)
    assembler.summarizer = LLMSummarizer(provider, model="mock-model")

    result = await assembler.build(
        tool_catalog=[],
        rules="rules",
        memory=[],
        history=["old-" + "x" * 200, "old-" + "y" * 200, "latest"],
    )

    assert result.contains_priority("summary")
    assert result.text.count("latest") == 1
    assert "old1" not in result.text


@pytest.mark.asyncio
async def test_assembler_keeps_raw_history_within_budget():
    class CountingSummarizer:
        calls = 0

        async def summarize(self, segments, task_id):
            self.calls += 1
            return "summary"

    assembler = ContextAssembler(max_tokens=1000)
    summarizer = CountingSummarizer()
    assembler.summarizer = summarizer
    result = await assembler.build(
        tool_catalog=[],
        rules="rules",
        memory=[],
        history=["round1", "round2", "round3", "round4", "round5: final check"],
    )

    assert result.contains_priority("round1")
    assert result.contains_priority("round5: final check")
    assert summarizer.calls == 0


@pytest.mark.asyncio
async def test_assembler_summarizes_dropped_history_when_over_budget():
    class CountingSummarizer:
        calls = 0

        async def summarize(self, segments, task_id):
            self.calls += 1
            return "summary"

    assembler = ContextAssembler(max_tokens=30, token_estimator=len)
    summarizer = CountingSummarizer()
    assembler.summarizer = summarizer
    result = await assembler.build(
        tool_catalog=[],
        rules="rules",
        memory=[],
        history=["x" * 100, "y" * 100, "latest"],
    )

    assert summarizer.calls == 1
    assert result.contains_priority("summary")
    assert result.contains_priority("latest")


@pytest.mark.asyncio
async def test_assembler_caches_summary_for_unchanged_history():
    class CountingSummarizer:
        calls = 0

        async def summarize(self, segments, task_id):
            self.calls += 1
            return "summary"

    assembler = ContextAssembler(max_tokens=30, token_estimator=len)
    summarizer = CountingSummarizer()
    assembler.summarizer = summarizer
    history = ["x" * 100, "y" * 100, "latest"]

    for _ in range(3):
        await assembler.build(
            tool_catalog=[],
            rules="rules",
            memory=[],
            history=history,
        )

    assert summarizer.calls == 1


@pytest.mark.asyncio
async def test_assembler_increments_summary_for_new_old_history():
    class RecordingSummarizer:
        def __init__(self):
            self.calls = []

        async def summarize(self, segments, task_id):
            self.calls.append(list(segments))
            return f"summary-{len(self.calls)}"

    assembler = ContextAssembler(max_tokens=30, token_estimator=len)
    summarizer = RecordingSummarizer()
    assembler.summarizer = summarizer
    old1 = "x" * 100
    old2 = "y" * 100

    await assembler.build(
        tool_catalog=[],
        rules="rules",
        memory=[],
        history=[old1, "latest1"],
    )
    await assembler.build(
        tool_catalog=[],
        rules="rules",
        memory=[],
        history=[old1, "latest1"],
    )
    await assembler.build(
        tool_catalog=[],
        rules="rules",
        memory=[],
        history=[old1, old2, "latest2"],
    )

    assert len(summarizer.calls) == 2
    assert old1 in summarizer.calls[0][0]
    incremental = summarizer.calls[1]
    assert incremental[0].startswith("Previous summary:")
    assert old1 not in incremental[1]
    assert old2 in incremental[1]


@pytest.mark.asyncio
async def test_assembler_evicts_old_summary_states():
    class CountingSummarizer:
        def __init__(self):
            self.calls = {}

        async def summarize(self, segments, task_id):
            self.calls[task_id] = self.calls.get(task_id, 0) + 1
            return "summary"

    assembler = ContextAssembler(
        max_tokens=30,
        token_estimator=len,
        summary_limit=2,
    )
    summarizer = CountingSummarizer()
    assembler.summarizer = summarizer
    history = ["x" * 100, "y" * 100, "latest"]

    for task_id in ("t1", "t2", "t3"):
        await assembler.build(
            tool_catalog=[],
            rules="rules",
            memory=[],
            history=history,
            task_id=task_id,
        )
    await assembler.build(
        tool_catalog=[],
        rules="rules",
        memory=[],
        history=history,
        task_id="t1",
    )

    assert summarizer.calls["t1"] == 2


@pytest.mark.asyncio
async def test_assembler_falls_back_when_provider_fails(caplog):
    class FailingProvider:
        async def complete(self, request):
            raise RuntimeError("provider failed")

    assembler = ContextAssembler(max_tokens=100)
    assembler.summarizer = LLMSummarizer(FailingProvider(), model="mock-model")
    result = await assembler.build(
        tool_catalog=[],
        rules="rules",
        memory=[],
        history=["old-" + "x" * 200, "old-" + "y" * 200, "latest"],
    )

    assert result.contains_priority("latest")
    assert result.text.count("latest") == 1
    assert "LLM summarization failed" in caplog.text


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
        invoked = False

        async def summarize(self, segments, task_id):
            self.invoked = True
            raise RuntimeError("summarizer failed")

    summarizer = FailingSummarizer()
    assembler = ContextAssembler(max_tokens=30, token_estimator=len)
    assembler.summarizer = summarizer
    result = await assembler.build(
        tool_catalog=[],
        rules="rules",
        memory=[],
        history=["x" * 100, "y" * 100, "latest"],
    )

    assert summarizer.invoked is True
    assert result.text.count("latest") == 1
    assert "x" * 100 not in result.text
    assert "y" * 100 not in result.text


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
