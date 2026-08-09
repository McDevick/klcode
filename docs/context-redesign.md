# KL Code 上下文系统重构方案

> 状态：设计待批准（2026-08-08）
> 范围：ContextAssembler / AgentLoop 上下文组装
> 关联：docs/promise_state.md（§3.8 已 100%，本方案为升级而非修复）

## 1. 目标

把 ContextAssembler + AgentLoop 的上下文组装从"预算内拼接"升级为**四层记忆系统**——固定层（规则）、状态层（任务状态）、事实层（分层记忆 + 用户指令沉淀）、轨迹层（分桶历史 + 落盘引用）——并补齐 token 记账与循环级预算。

核心效果：让 agent **要点级记住用户说过的话**（跨任务约束持续生效），且每层机制可单测、不依赖 LLM。

## 2. 明确不做

- 向量检索 / embedding（违反"无外部依赖、机制可测试"哲学）
- 跨 session 的项目级语义记忆（本方案做 session 级，项目级留待后续）
- 改变 provider 消息协议（保持 OpenAI 兼容格式）

## 3. 架构（四层 + 数据流）

```
┌─ 固定层（每轮全量，预算优先级最高）───────────┐
│  SYSTEM_PROMPT（合并为单条 system，兼容性）      │
│  规则：用户沉淀 > 全局用户规则 > 项目规则 > 默认 │
│  工具目录（tools 参数，不占预算）                │
├─ 状态层（每轮刷新，不摘要）─────────────────────┤
│  task_plan（done/pending 结构化）               │
│  续接上下文（跨任务 outcome/files/next_step）    │
├─ 事实层（按需注入，配额制）─────────────────────┤
│  记忆：kind 配额 + 关键词相关 Top N（替代最近5条）│
│  用户指令沉淀：约束/偏好/流程（Phase 2 新增）     │
├─ 轨迹层（预算内，分桶）────────────────────────┤
│  桶A 对话/决策：最近 N 轮 + 旧桶结构化摘要        │
│  桶B 工具结果：最近 K 个 + 旧引用 ~/.kl/tool_outputs│
│  桶C 反馈/观察：同类合并去重                     │
└────────────────────────────────────────────────┘
        │ 每轮：used_tokens 记账 → 累计到 Task
        ▼
  循环级预算（超限 → 任务失败保留现场）
```

## 4. 实施阶段（每阶段独立可合并）

### Phase 1：记忆分层注入 + 检索升级（store.py + context.py + agent_loop.py）

1. `memory` 表加 `created_at` 列（SQLite `ALTER TABLE ADD COLUMN DEFAULT`，向后兼容）
2. `MemoryStore.find` 升级：`kind` 过滤 + `content LIKE` 关键词匹配 + `LIMIT`（替代全表扫描 + Python 过滤，顺带修性能问题）
3. 注入策略改为**按 kind 配额**：用户 note 2 条 + feedback 结论 2 条 + context_summary 1 条 + 关键词相关 Top N（从任务描述取词）
4. **停止注入 tool_result 原始记忆**（与 history 的 `role: tool` 消息重复，双份占预算）——数据仍写库（审计用），仅不进上下文

- 验证：test_memory（过滤/关键词/限额）、test_context（配额注入断言）
- 合并后即可用：相关性替代时间序，预算立省约 30%（重复消除）

### Phase 2：用户指令沉淀（新模块 `core/instruction_sediment.py`）

1. **捕获**：`add_instruction`（用户 note）→ 全部捕获；任务描述 → 仅开头用户消息
2. **分类**（纯规则，可测试）：否定词（不要/别/禁止/避免）→ 约束；正向偏好（用/优先/统一/保持）→ 偏好；时序（先/然后/最后）→ 流程；无匹配 → 不沉淀
3. **存储**：`state` 表 `(session:{id}, user_instructions)`，JSON 数组含 `{text, category, source_task, created_at}`；同文本去重
4. **注入**：任务开始（与 continuation 并列）+ 每轮 assembled 轻量注入；带来源标记 `[用户约束] 别动 README（任务 t3 提出）`
5. **防误伤**：只沉淀"指令语态"消息（note 天然满足）；重复出现 2 次的约束提示提升为项目规则（可选，Phase 2 只做 session 级）

- 验证：test_instruction_sediment（分类各分支、去重、注入格式）

### Phase 3：历史分桶压缩（agent_loop.py + context.py）

1. history 运行时划分为三桶：A 对话/决策（user 文本 + assistant 文本）、B 工具结果（role: tool）、C 反馈/观察（feedback 前缀 user 消息）
2. `should_compress`/`compact_history` 桶感知：
   - 桶 A：保留最近 N 轮，旧桶交给 LLMSummarizer（保留现有增量摘要）
   - 桶 B：只留最近 K 个完整结果，更早的替换为 `~/.kl/tool_outputs/<file>` 引用（复用已有落盘机制）
   - 桶 C：同类（同 category）只留最新一条
3. 摘要失败 fallback：桶 A 保留最近 4 轮原始（现状行为，不回归）

- 验证：test_agent_loop（压缩后三桶内容断言：A 有摘要、B 只剩引用、C 去重）

### Phase 4：token 记账 + 循环级预算（context.py + models/task.py + agent_loop.py + routes.py）

1. `AssembledContext.used_tokens` 每轮累计 → Task 新增 `token_usage` 字段（DB 迁移，向后兼容）——顺带兑现 §6 数据模型承诺
2. 循环级停止条件：累计 token > `max_tokens_budget`（LoopSettings 新增，默认如 200k）→ 任务 FAILED + summary 精确记录——顺带兑现 §3.3 P1 缺口
3. `GET /tasks/{id}` 返回 token 用量（兑现 §4.4 状态接口承诺）

- 验证：test_agent_loop（预算触发失败）、test_routes（token 字段）

## 5. 关键决策

1. **记忆注入 = 配额 + 关键词相关，不做向量**——项目哲学优先（可测试、无外部依赖）
2. **用户指令沉淀用纯规则分类**——"机制可测试"承诺；误分类用三层防御兜底（指令语态限定 / 来源标记可追溯 / 同文本去重）
3. **tool_result 记忆停止注入**——与 history 重复是当前最大预算浪费；数据保留在库（审计不丢）
4. **分桶压缩依赖已有 tool_outputs 落盘**——Phase 3 纯接线，无新基建
5. **token 预算从"装配参数"升级为"循环控制手段"**——SPEC §3.3/§4.1 原始语义（预算用尽即停）

## 6. 被拒绝的取舍

- 向量检索：embedding 依赖 + 不可确定性测试，与项目根基冲突
- 穷举式保留全部历史：agent 窗口小、任务长，不可行；要点级记忆是正确目标
- LLM 分类沉淀指令：不可测试、每轮成本高；纯规则优先，效果不足再评估

## 7. 最脆弱假设

**Phase 2 分类器精度**。若纯规则把正常文本误分类为约束 → 沉淀噪声。防御已在设计内（指令语态限定 + 来源标记 + 去重）；若实测仍失败，回退方案：沉淀前 TUI 一步确认（成本 +1 交互点）。

## 8. 数据迁移与回滚

- 两处 `ALTER TABLE ADD COLUMN`（memory.created_at、tasks.token_usage）均带默认值，向后兼容，可回滚
- 每阶段独立合并、独立回滚；Phase N 上线后系统完全可用，即使 N+1 不做

## 9. 文件清单（12 个）

- 修改：`core/context.py`、`core/agent_loop.py`、`memory/store.py`、`models/task.py`、`storage/database.py`、`api/routes.py`
- 新增：`core/instruction_sediment.py`、`tests/test_instruction_sediment.py`
- 测试：`tests/test_context.py`、`tests/test_memory.py`、`tests/test_agent_loop.py`、`tests/test_routes.py`

## 10. 验证命令

```bash
# 每阶段合并前
python -m pytest server/tests -q      # 全量 server
cd cli && npm test                    # cli 不回归

# 手动验收（Phase 1/3 后）
# 跑一个长任务，观察 /context 面板：预算占用、记忆分布、桶结构
```

## 11. 交付顺序

Phase 1（记忆分层）→ Phase 2（用户指令沉淀）→ Phase 3（分桶压缩）→ Phase 4（token 记账）

**Phase 1+2 组合即实现"记住用户说的话"效果**（跨任务约束持续生效）；Phase 3/4 是效率与成本控制。

## 12. 明确延迟的未知项

- 关键词匹配的停用词表（实施时用任务描述分词去常见词即可）
- Phase 2"提升为项目规则"的确认交互（Phase 2 完成后评估是否值得做）
