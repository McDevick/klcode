import pytest

from kl_server.core.instruction_sediment import (
    classify_instruction,
    format_instruction,
    format_user_instructions,
    load_user_instructions,
    save_user_instruction,
)
from kl_server.memory.store import MemoryStore


def test_classify_instruction_branches():
    assert classify_instruction("不要修改 README") == "constraint"
    assert classify_instruction("优先使用 pytest") == "preference"
    assert classify_instruction("先跑测试，然后提交") == "flow"
    assert classify_instruction("这个文件包含接口定义") is None


def test_format_instruction_with_source():
    assert format_instruction(
        {
            "text": "别动 README",
            "category": "constraint",
            "source_task": "t3",
        }
    ) == "[用户约束] 别动 README（任务 t3 提出）"


def test_format_user_instructions_caps_to_latest():
    records = [
        {
            "text": f"不要改文件{i}",
            "category": "constraint",
            "source_task": f"t{i}",
        }
        for i in range(10)
    ]

    text = format_user_instructions(records)

    assert "文件1" not in text
    assert "文件2" in text
    assert "文件9" in text
    assert text.count("[用户约束]") == 8


@pytest.mark.asyncio
async def test_save_user_instruction_stores_and_dedupes(tmp_path):
    store = MemoryStore(tmp_path / "memory.db")
    await store.connect()
    try:
        assert await save_user_instruction(
            store,
            "s1",
            "t1",
            "不要修改 README",
        ) is True
        assert await save_user_instruction(
            store,
            "s1",
            "t2",
            "不要修改 README",
        ) is False
        assert await save_user_instruction(
            store,
            "s1",
            "t3",
            "这个文件包含接口定义",
        ) is False

        records = await load_user_instructions(store, "s1")

        assert len(records) == 1
        assert records[0]["text"] == "不要修改 README"
        assert records[0]["category"] == "constraint"
        assert records[0]["source_task"] == "t1"
    finally:
        await store.close()
