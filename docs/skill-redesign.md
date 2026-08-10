# KL Code Skill 渐进式披露重设计

> 状态：实现中，Phase 1/2 已完成（2026-08-10）
> 已实现：SkillLoader frontmatter/index/rank/load/load_section/context_for_task；read_skill 工具；AgentLoop L1 注入；`/skills` 结构化；TUI 元数据展示；旧 skill 兼容
> 范围：SkillLoader / AgentLoop / ContextAssembler / 工具注册 / TUI `/skills`
> 关联：docs/context-redesign.md（上下文分级）、docs/mcp-redesign.md（workspace-aware MCP）、docs/promise_state.md（§3.9）
> 触发：当前 skill 按目录名命中后整篇注入，未命中则完全不可见，缺少渐进式披露与按需展开能力

## 1. 现状与问题

当前 `server/kl_server/skills/loader.py` 的行为：

```text
任务文本包含 skill 目录名
  -> 读取整个 SKILL.md
  -> 拼接后注入上下文

任务文本不包含 skill 目录名
  -> 完全不注入
```

由此产生几个问题：

1. **全有或全无**：命中后占用大量上下文；未命中时模型不知道有这个能力。
2. **匹配面太窄**：目录名不一定等于用户自然语言里的说法，例如目录叫 `leetcode`，任务说“做一道算法题”可能不命中。
3. **缺少元数据**：当前只有名称和一段 description，没有 keywords、when_to_use、summary、章节结构。
4. **缺少按需入口**：模型没有 `read_skill` 类工具，不能自己决定在需要时展开详细流程。
5. **大 skill 无法分层**：整篇 SKILL.md 可能包含流程、模板、示例、检查清单，全部一次性注入不划算。

## 2. 目标

把 skill 从“目录名碰运气”升级为三级渐进式披露：

```text
L0 全局技能索引
  常驻上下文，只放名称、一句话描述、触发关键词

L1 任务相关摘要
  新任务开始时，按确定性匹配选出候选 skill
  只注入 summary / description，不注入完整步骤

L2 按需展开
  agent 调用 read_skill(name) 获取完整 SKILL.md

L3 分节展开
  大型 skill 支持 read_skill(name, section)
  只读取当前需要的章节
```

核心目标：

- 上下文开销小，模型始终知道“有哪些 skill”；
- 任务匹配比目录名更可靠；
- 模型可以按需获取详细内容；
- 不依赖 embedding / 外部模型；
- 旧 skill 目录无需迁移即可继续工作；
- 新 skill 无需重启后端即可被新任务发现。

## 3. 明确不做

- 第一版不做向量检索 / embedding。
- 不引入项目级 skill（继续使用全局 `~/.kl/skills`）。
- 不默认把任何 skill 全量注入所有任务。
- 不把 skill 匹配交给 LLM 判断（第一阶段保持确定性、可测试）。
- 不自动安装或拉取 skill。
- 不做 skill 市场 / 订阅机制。

## 4. 架构

### 4.1 SKILL.md 新格式

推荐结构化 frontmatter：

```markdown
---
name: leetcode
description: 算法题的解题、编码、测试流程
keywords:
  - leetcode
  - 算法
  - cpp
  - 题目
when_to_use: 用户要求根据题目生成代码或调试算法题
summary: |
  先分析题目结构和边界条件，再编码并用测试验证；
  代码写入用户指定目录，未指定时使用 tmp。
always_on: false
---

## Workflow

...

## Examples

...
```

字段约定：

| 字段 | 必填 | 用途 |
|---|---|---|
| `name` | 否 | skill 显示名；缺省使用目录名 |
| `description` | 推荐 | 一句话能力描述，用于 L0 索引 |
| `keywords` | 推荐 | 触发词，用于 L1 排名 |
| `when_to_use` | 推荐 | 适用场景说明，用于 L1 摘要 |
| `summary` | 推荐 | 渐进式披露中的 L1 摘要 |
| `always_on` | 否 | 是否总是进入上下文，默认 `false` |

### 4.2 SkillLoader 接口

```python
class SkillLoader:
    def index(self) -> list[dict]:
        """返回全部 skill 的元数据，用于 L0 和 /skills。"""

    def rank(self, task: str, limit: int = 5) -> list[dict]:
        """按任务文本与 skill 元数据做确定性排序，返回 L1 摘要。"""

    def load(self, name: str) -> str:
        """返回指定 skill 的完整 SKILL.md，用于 L2。"""

    def load_section(self, name: str, section: str) -> str:
        """返回指定 skill 的某个章节，用于 L3。"""

    def context_for_task(self, task: str, limit: int = 5) -> str:
        """组合 L0 索引与 L1 候选摘要，替代当前 load([task])。"""
```

### 4.3 数据流

```text
SkillLoader.index()
  -> 注入系统提示词 [可用 Skills]

新任务开始
  -> SkillLoader.rank(task, limit=5)
  -> 注入候选 skill 摘要到上下文

agent 判断 skill 适用
  -> 调用 read_skill(name)
  -> 返回完整 SKILL.md

skill 很大或只需要某部分
  -> 调用 read_skill(name, section="Workflow")
  -> 返回对应章节
```

### 4.4 L0 全局索引

索引格式示例：

```text
[可用 Skills]
- leetcode: 算法题的解题、编码、测试流程
  触发: leetcode, 算法, cpp, 题目
- test-driven: 测试先行开发流程
  触发: tdd, 测试, 单测
```

注入规则：

- 所有非 `always_on` skill 只暴露 L0 索引；
- `always_on: true` 的 skill 直接注入摘要，不经过排名；
- 索引总量应有限制，例如默认最多显示 30 个，超出时按名称截断并提示；
- 索引本身不包含完整 SKILL.md。

### 4.5 L1 确定性排名

评分规则：

```text
任务文本包含 skill 目录名或 name
  -> 最高分

任务文本包含 keywords 中任一关键词
  -> 高权重

任务文本与 description / when_to_use 有 token 重叠
  -> 中等权重

无匹配
  -> 不进入 L1，但仍出现在 L0 索引
```

排序：

```text
score 降序
同分时按 name 升序
```

默认只注入前 5 个候选摘要，防止上下文膨胀。

不使用向量检索，因为：

- 确定性排序可单测；
- 无外部依赖；
- 目录名 + keywords + description 已经能覆盖大多数场景；
- 未来若效果不足，再在 `rank()` 内部增加 embedding 实现，不影响外部接口。

### 4.6 L2 `read_skill` 工具

新增内置工具：

```text
name: read_skill
description: 读取指定 skill 的完整说明；只有模型确认该 skill 适用时才调用
schema:
  type: object
  properties:
    name:
      type: string
    section:
      type: string
  required:
    - name
```

行为：

- `name` 不存在 -> `ToolResult(ok=False, error="skill not found: <name>")`
- 只传 `name` -> 返回完整 `SKILL.md`
- 传 `name + section` -> 按 markdown 标题定位章节并返回
- 完整内容超过工具输出上限 -> 落盘到 tool_outputs，返回截断内容 + 文件引用

### 4.7 L3 分节展开

`load_section(name, section)` 按 `## 标题` 切分：

```text
## Workflow
...

## Examples
...
```

匹配规则：

- 大小写不敏感；
- 支持精确标题名；
- 找不到时返回所有一级/二级标题作为目录，提示可用 section 名；
- section 内容同样受输出上限保护。

## 5. Agent 上下文接线

### 5.1 当前接入点

`server/kl_server/core/agent_loop.py` 当前在任务开始时调用：

```python
skills=self.skills.load([task])
```

替换为：

```python
skills=self.skills.context_for_task(task, limit=5)
```

### 5.2 注入内容

`context_for_task()` 返回：

```text
[可用 Skills]
- leetcode: ...
  触发: ...

[任务相关 Skill]
- leetcode
  适用: 用户要求根据题目生成代码或调试算法题
  摘要: 先分析题目结构和边界条件，再编码并用测试验证...
```

系统提示词中追加一句：

```text
如果某个 Skill 适用，先读取 read_skill(name) 的完整说明，再按其中流程执行。
```

### 5.3 工具注册

`read_skill` 在 bootstrap 中注册，持有当前 `SkillLoader`：

```python
register_skill_tools(tool_registry, skills)
```

权限声明：

```text
permissions = ["skill"]
sandbox = {"read_only": True}
timeout = 10.0
```

## 6. TUI `/skills`

### 6.1 现有行为

`/skills` 每次打开时调用 `GET /api/v1/skills`，后端调用 `skills.list()`。

### 6.2 升级后展示

`GET /api/v1/skills` 返回结构化元数据：

```json
{
  "name": "leetcode",
  "description": "算法题的解题、编码、测试流程",
  "keywords": ["leetcode", "算法", "cpp", "题目"],
  "when_to_use": "用户要求根据题目生成代码或调试算法题",
  "always_on": false,
  "sections": ["Workflow", "Examples"]
}
```

TUI 只展示 skill 名称，避免面板信息过载。完整内容由 agent 在任务中通过 `read_skill(name)` 按需读取。

## 7. 兼容性与回退

### 7.1 旧 skill 兼容

没有 frontmatter 的 `SKILL.md`：

- `name` 使用目录名；
- `description` 使用第一个非标题、非空行；
- `keywords` 使用目录名；
- `summary` 使用 description 前 200 字符；
- `always_on` 为 `false`。

### 7.2 frontmatter 损坏

- YAML 解析失败时回退到旧行为；
- 记录 warning，不阻塞 skill 列表和任务执行；
- 不要求用户迁移旧 skill。

### 7.3 缓存

继续不缓存文件内容，保证新增/修改 skill 后新任务立即生效。

## 8. 边界场景

| 场景 | 行为 |
|---|---|
| 新增 skill | 下次 `/skills` 和新任务立即可见，无需重启 |
| 修改 SKILL.md | 下次任务和 read_skill 读取新内容 |
| 任务命中目录名 | 进入 L1，并保留高排名 |
| 任务命中 keywords | 进入 L1 |
| 任务无任何匹配 | 不注入候选，但 L0 索引仍在 |
| `always_on: true` | 摘要始终进入上下文 |
| skill 内容很大 | 不整篇注入；由模型按需 read_skill |
| section 不存在 | 返回可用 section 目录 |
| skill 不存在 | read_skill 返回明确错误 |
| 大文档超输出上限 | 截断 + tool_outputs 文件引用 |

## 9. 实施阶段

### Phase 1：元数据 + L0/L1 + read_skill

1. `SkillLoader` 增加 frontmatter 解析、`index()`、`rank()`、`load(name)`。
2. `context_for_task()` 替代 `load([task])`。
3. 注册 `read_skill` 工具。
4. `/skills` 返回结构化 metadata。
5. 旧 skill 兼容逻辑。

### Phase 2：分节展开

1. `load_section(name, section)`。
2. `read_skill` schema 增加 `section`。
3. 不做 `/skills` 完整内容预览；TUI 只展示 skill 名称。

### Phase 3：使用情况与优化

1. 记录 `read_skill` 调用次数和 skill 使用频率。
2. 若 L1 误匹配明显，调整关键词权重。
3. 若仍需要语义匹配，再评估 embedding。

每阶段可独立合并，Phase 1 上线后旧 skill 依然可用。

## 10. 测试计划

### 10.1 单元测试

- frontmatter 解析：完整字段、缺省字段、非法 YAML 回退；
- `index()`：排序、过滤无 SKILL.md 的目录；
- `rank()`：目录名命中、keyword 命中、description 命中、无匹配；
- `context_for_task()`：只包含 L0 + L1，不包含完整 SKILL.md；
- `read_skill`：完整读取、分节读取、未知 skill、未知 section；
- `always_on`：始终进入上下文；
- 大文档截断与 tool_outputs 引用。

### 10.2 回归测试

- 现有 `test_skills.py` 全部保留并通过；
- `agent_loop` 上下文断言不再出现整篇 skill；
- TUI `/skills` 接口返回字段向后兼容。

### 10.3 手动验收

```text
1. 在 ~/.kl/skills/leetcode/SKILL.md 添加带 frontmatter 的 skill
2. /skills 显示 leetcode 及关键词
3. 新任务输入“做一道算法题”
4. 上下文出现 leetcode 摘要，而不是完整 SKILL.md
5. agent 调用 read_skill("leetcode") 后按完整流程执行
6. read_skill("leetcode", section="Workflow") 只返回 Workflow 章节
```

## 11. 文件清单

| 文件 | 改动 |
|---|---|
| `server/kl_server/skills/loader.py` | frontmatter 解析、index/rank/load/load_section/context_for_task |
| `server/kl_server/core/agent_loop.py` | `load([task])` 替换为 `context_for_task(task)` |
| `server/kl_server/core/context.py` | 无需改动；skills 继续以字符串注入 |
| `server/kl_server/tools/builtin/skills.py` | 新增 `read_skill` 工具 |
| `server/kl_server/tools/builtin/__init__.py` | 未直接改动；由 bootstrap 单独注册 read_skill |
| `server/kl_server/bootstrap.py` | 将 SkillLoader 注入 skill 工具 |
| `server/kl_server/api/routes.py` | `/skills` 返回结构化 metadata；可选预览端点 |
| `server/tests/test_skills.py` | 新增元数据、排名、分节、工具测试 |
| `server/tests/test_agent_loop.py` | 未单独新增；由 test_extensions 覆盖 |
| `server/tests/test_routes.py` | `/skills` 结构化返回 |
| `cli/src/api/client.ts` | SkillInfo 增加 keywords/when_to_use/summary/always_on/sections |
| `cli/src/tui/components/skills-menu.tsx` | 只展示 skill 名称 |
| `docs/release-test.md` | 增加 skill 渐进式披露验收项 |

## 12. 风险与缓解

| 风险 | 缓解 |
|---|---|
| 模型不主动调用 `read_skill` | L1 摘要足够明确；系统提示词给出调用规则；`always_on` 兜底 |
| 关键词误匹配 | 排名用权重而非命中即注入；提供 when_to_use 说明 |
| 索引本身膨胀 | 限制 L0 数量；description 强制 200 字符内 |
| 大 skill 截断 | 分节读取 + tool_outputs 引用 |
| frontmatter 破坏旧 skill | 解析失败回退旧行为，并保留现有测试 |

## 13. 验收命令

```bash
python -m pytest server/tests -q
cd cli && npm test
npx tsc --noEmit
```

手动检查：

```text
/skills 显示元数据
新任务触发 L1 摘要
agent 通过 read_skill 展开完整流程
```
