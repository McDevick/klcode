"""Pure-rule user instruction sediment for session-level persistence."""

import json
from datetime import datetime, timezone

USER_INSTRUCTIONS_STATE_KIND = "user_instructions"
# 任务描述默认参与沉淀；如后续发现噪声，可只保留 note 沉淀。
SEDIMENT_TASK_DESCRIPTIONS = True
INSTRUCTION_LABELS = {
    "constraint": "用户约束",
    "preference": "用户偏好",
    "flow": "用户流程",
}
MAX_INJECTED_INSTRUCTIONS = 8
MAX_STORED_INSTRUCTIONS = 100

_NEGATIVE_MARKERS = (
    "不要",
    "别",
    "禁止",
    "避免",
    "不能",
    "不得",
    "不允许",
    "切勿",
    "勿",
)
_PREFERENCE_MARKERS = (
    "优先",
    "统一",
    "保持",
    "使用",
    "推荐",
    "尽量",
    "采用",
    "用",
)
_FLOW_MARKERS = (
    "然后",
    "最后",
    "随后",
    "再",
    "完成后",
)


def classify_instruction(text: str) -> str | None:
    """纯规则分类：否定 -> 约束，时序 -> 流程，正向偏好 -> 偏好。"""
    content = (text or "").strip()
    if not content:
        return None
    if any(marker in content for marker in _NEGATIVE_MARKERS):
        return "constraint"
    flow_content = content.replace("优先", "")
    if (
        "先" in flow_content
        or any(marker in content for marker in _FLOW_MARKERS)
    ):
        return "flow"
    if any(marker in content for marker in _PREFERENCE_MARKERS):
        return "preference"
    return None


def format_instruction(record: dict) -> str:
    """把沉淀记录渲染成带来源的上下文条目。"""
    category = record.get("category")
    label = INSTRUCTION_LABELS.get(category, "用户指令")
    text = str(record.get("text", "")).strip()
    source = str(record.get("source_task", "")).strip()
    if not text:
        return ""
    if source:
        return f"[{label}] {text}（任务 {source} 提出）"
    return f"[{label}] {text}"


def format_user_instructions(records: list[dict]) -> str:
    rendered = [
        formatted
        for record in records
        if (formatted := format_instruction(record))
    ]
    return "\n".join(rendered[-MAX_INJECTED_INSTRUCTIONS:])


async def load_user_instructions(memory, session_id: str) -> list[dict]:
    if memory is None or not hasattr(memory, "get_state"):
        return []
    try:
        raw = await memory.get_state(
            f"session:{session_id}",
            USER_INSTRUCTIONS_STATE_KIND,
        )
    except Exception:
        return []
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return []
    if not isinstance(data, list):
        return []
    return [item for item in data if isinstance(item, dict)]


async def save_user_instruction(
    memory,
    session_id: str,
    task_id: str,
    text: str,
) -> bool:
    """分类后写入 user_instructions；同文本去重，无匹配不沉淀。"""
    if memory is None or not hasattr(memory, "get_state") or not hasattr(memory, "set_state"):
        return False
    category = classify_instruction(text)
    if category is None:
        return False
    normalized = (text or "").strip()
    if not normalized:
        return False
    records = await load_user_instructions(memory, session_id)
    if any(str(item.get("text", "")) == normalized for item in records):
        return False
    records.append(
        {
            "text": normalized,
            "category": category,
            "source_task": task_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
    )
    stored = records[-MAX_STORED_INSTRUCTIONS:]
    await memory.set_state(
        f"session:{session_id}",
        USER_INSTRUCTIONS_STATE_KIND,
        json.dumps(stored, ensure_ascii=False),
    )
    return True
