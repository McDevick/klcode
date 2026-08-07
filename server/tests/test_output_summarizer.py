import pytest

from kl_server.core.output_summarizer import OutputSummarizer
from kl_server.models.action import ToolResult


@pytest.mark.asyncio
async def test_summarizer_extracts_command_failure():
    summarizer = OutputSummarizer()
    result = ToolResult(
        ok=True,
        output=(
            '{"exit_code": 1, "stdout": "1 failed\\nAssertionError: x != y", '
            '"stderr": "", "truncated": false}'
        ),
    )

    summary = await summarizer.summarize("run_tests", {}, result, "t1")

    assert "exit_code: 1" in summary
    assert "test_failure" in summary
    assert "AssertionError" in summary


@pytest.mark.asyncio
async def test_summarizer_extracts_command_success_tail():
    summarizer = OutputSummarizer()
    result = ToolResult(
        ok=True,
        output=(
            '{"exit_code": 0, "stdout": "first\\nsecond", '
            '"stderr": "", "truncated": false}'
        ),
    )

    summary = await summarizer.summarize("run_command", {}, result, "t1")

    assert "status: success" in summary
    assert "second" in summary


@pytest.mark.asyncio
async def test_summarizer_read_file_keeps_head_tail():
    summarizer = OutputSummarizer()
    output = "\n".join(f"line {index}" for index in range(100))
    result = ToolResult(ok=True, output=output)

    summary = await summarizer.summarize(
        "read_file",
        {"path": "src/a.ts"},
        result,
        "t1",
    )

    assert "path: src/a.ts" in summary
    assert "lines: 100" in summary
    assert "line 0" in summary
    assert "line 99" in summary


@pytest.mark.asyncio
async def test_summarizer_grep_keeps_match_count_and_preview():
    summarizer = OutputSummarizer()
    output = "\n".join(f"src/file_{index}.py" for index in range(30))
    result = ToolResult(ok=True, output=output)

    summary = await summarizer.summarize(
        "grep",
        {"pattern": "todo"},
        result,
        "t1",
    )

    assert "matches: 30" in summary
    assert "src/file_0.py" in summary
    assert "src/file_29.py" in summary


@pytest.mark.asyncio
async def test_summarizer_uses_llm_for_large_unknown_output_and_caches():
    class FakeLlm:
        def __init__(self):
            self.calls = 0

        async def summarize_output(self, text, task_id):
            self.calls += 1
            return "llm summary"

    llm = FakeLlm()
    summarizer = OutputSummarizer(llm_summarizer=llm, llm_threshold=10)
    result = ToolResult(ok=True, output="x" * 100)

    first = await summarizer.summarize("custom_tool", {}, result, "t1")
    second = await summarizer.summarize("custom_tool", {}, result, "t1")

    assert first == "llm summary"
    assert second == "llm summary"
    assert llm.calls == 1


@pytest.mark.asyncio
async def test_summarizer_prefers_deterministic_for_large_command():
    class FakeLlm:
        def __init__(self):
            self.calls = 0

        async def summarize_output(self, text, task_id):
            self.calls += 1
            return "llm summary"

    llm = FakeLlm()
    summarizer = OutputSummarizer(llm_summarizer=llm, llm_threshold=8000)
    output = (
        '{"exit_code": 1, "stdout": "1 failed\\nAssertionError", "stderr": "'
        + "x" * 10_000
        + '", "truncated": true}'
    )
    result = ToolResult(ok=True, output=output)

    summary = await summarizer.summarize("run_tests", {}, result, "t1")

    assert "test_failure" in summary
    assert llm.calls == 0


@pytest.mark.asyncio
async def test_summarizer_falls_back_when_llm_fails():
    class FailingLlm:
        async def summarize_output(self, text, task_id):
            raise RuntimeError("llm down")

    summarizer = OutputSummarizer(
        llm_summarizer=FailingLlm(),
        llm_threshold=10,
    )
    result = ToolResult(ok=True, output="x" * 100)

    summary = await summarizer.summarize("custom_tool", {}, result, "t1")

    assert summary.startswith("truncated: true")
    assert "head:" in summary
    assert "tail:" in summary
