# SPEC_PROCESS：KL Code 设计过程记录

> 日期：2026-08-02  
> 关联提交：`3c4f815`（SPEC.md）、`cdf8a1a`（PLAN.md）

## 1. 过程概览

本文件记录 KL Code 从“做一个 coding agent”到 `SPEC.md`、`PLAN.md` 产出过程中的关键决策。设计使用 Superpowers `brainstorming` 和 `writing-plans` 技能，遵循“一次一个问题、设计分段确认、规格沉淀后再转计划”的流程。

最终形成的关键方向：

- 长期可用的本地 coding agent，不是只满足课程演示。
- 第一版形态为 `CLI + TUI`，后续扩展 WebUI。
- 服务端为 Python FastAPI，客户端为 TypeScript React Ink。
- 服务端承载完整 harness：主循环、工具分发、治理、反馈、记忆、上下文、审计。
- 治理是重点做深维度，反馈闭环和工具扩展提供基础实现。
- 支持 Git 与非 Git 工作区。
- 支持多供应商、MCP、skill、hook、用户 Python 工具插件。

## 2. 关键澄清问题与用户修正

### 2.1 项目定位

智能体最初按课程作业方向提问，用户明确：

> “更多是一个长期可用的编码工具”

决策：以长期工具为目标，同时保留课程交付物要求。这个修正影响了后续几乎所有设计，尤其是分发、凭据、可扩展性和“不能做成 demo”的工程深度。

### 2.2 技术形态

智能体先建议本地 CLI 优先。用户提出：

> “采用类似CS架构的设置采用python fastapi，然后前端后续的webui，现在的tui cli这里使用TS react，ink处理”

决策：采用 Python FastAPI 服务端 + TypeScript React Ink 客户端，第一版本地 daemon，预留远程部署。

### 2.3 重点机制

需求文档要求六个维度都有基础实现，并选择一个维度做深。智能体推荐“反馈闭环”，用户选择：

> “我更希望去做2治理，其他两个需要有最基本的功能”

决策：治理作为重点维度，反馈闭环和工具扩展作为基础实现。

### 2.4 工作区边界

智能体最初建议第一版强制 Git 仓库。用户追问：

> “agent必须在包含git仓库的情况下才能跑吗？”

并明确：

> “支持非git目录”

决策：设计为 `managed`（Git）和 `unmanaged`（非 Git 快照）两种工作区模式；非 Git 模式审批更严格。

### 2.5 工具范围

用户指出内置工具不足：

> “需要加入类似grep和glop的两个工具，此外还需要一个taskmange工具做任务编排”

智能体补充 `apply_patch`，用户接受。决策：第一版工具集包含文件、搜索、补丁、shell、git、验证、任务编排、MCP 和用户插件工具。

### 2.6 Subagent 方案

用户询问：

> “后续subagent，是要做成工具呢还是集成在系统里”

决策：采用混合方案。subagent 作为受治理的工具暴露给模型，但创建、审批、执行、回收、审计由 `TaskManager` 和 `AgentLoop` 管理。第一版不实现，仅记录为后续范围。

### 2.7 上下文压缩

用户担心：

> “这样时间长了上下文是不是会爆，我希望增加一个按token计量压缩上下文的机制”

智能体先建议第一版以确定性裁剪为主，用户拒绝：

> “我还是第一版，把LLM摘要整合进去吧，直接裁剪太容易失忆了”

决策：第一版集成 LLM 摘要，保留原始事件，摘要失败时使用结构化 fallback。

### 2.8 扩展性

用户要求 hook 可扩展、TUI 支持 `/skills`、退出指令和会话管理，并要求用户可配置自定义工具。决策：

- hook 支持 `command` 和 `http`。
- 斜杠指令通过 `CommandRegistry` 注册，后续可继续扩展。
- 用户工具通过 Python 插件 API 注册，不绕过治理。
- session 与 task 分层，支持恢复和持久化。

## 3. 三轮以上关键迭代节选

### 迭代 1：从“做 coding agent”到“长期本地工具”

原始设想接近课程作业。brainstorming 先澄清定位，用户回答“长期可用”。这次迭代修正了规模预期：不能只做可演示机制，还必须考虑新机器安装、凭据、分发、长期维护和后续扩展。

最终写入 SPEC：目标用户为个人开发者，第一版稳定完成真实小任务，架构面向复杂任务、WebUI、远程和 subagent。

### 迭代 2：从“用户提出技术栈”到“Harness Server + Thin Client”

用户提出 FastAPI + Ink 的 CS 架构。智能体继续确认服务端部署方式后给出三种架构：

1. Harness Server + Thin Client
2. Sidecar-per-session
3. Smart Client + Thin Server

用户选择方案 A。这次迭代把“agent 内核在哪里”锁定：主循环、治理、反馈、记忆都在 FastAPI 服务端，TUI 只做展示和控制。

### 迭代 3：从“反馈做深”到“治理做深”

需求要求选择重点维度。智能体推荐反馈闭环，用户选择治理。随后治理设计细化为 `ScopeFence -> SandboxPolicy -> DangerClassifier -> HITL -> Executor`，并要求沙箱、审批状态机、非 Git 快照和审计日志都可脱离 LLM 测试。

### 迭代 4：从“工具少”到“完整工具系统”

用户要求 `grep`、`glob`、`task_manage`，智能体补充 `apply_patch`，并给出工具扩展方案。用户还要求工具崩溃不能拖垮 agent loop，系统提示词要包含工具描述。这些要求进入 `PLAN.md` 的 `ToolExecutor` 和上下文装配任务。

### 迭代 5：从“上下文防爆”到“第一版 LLM 摘要”

用户提出 token 计量压缩，智能体最初建议第一版只做确定性裁剪。用户反对直接裁剪，要求第一版整合 LLM 摘要。设计改为：上下文分段预算、历史片段摘要、原始日志保留、摘要失败 fallback。对应 `PLAN.md` 的 ContextAssembler 和 LLMSummarizer 任务。

## 4. 被采纳与被推翻的建议

### 被采纳

- 长期工具优先，同时满足课程交付。
- 第一版 CLI/TUI，后续 WebUI。
- 本地 daemon 优先，预留远程。
- Harness Server + Thin Client。
- 单 agent 主循环先行，subagent 后续。
- 每任务默认新建分支，非 Git 使用快照。
- 多供应商抽象。
- 治理做深。
- `apply_patch` 加入第一版工具集。
- subagent 做成受治理的工具。
- 用户工具使用 Python 插件 API。
- hook 支持 `command` 和 `http`。
- 第一版集成 LLM 摘要。
- TUI 配置向导、会话系统、`/skills`、`/exit` 和可扩展命令注册表。

### 被推翻或修正

- 智能体最初按课程作业方向提问，被用户修正为长期工具。
- 智能体建议第一版只做 Git 仓库，被用户修正为同时支持非 Git 目录。
- 智能体建议第一版上下文压缩以确定性裁剪为主，被用户修正为第一版就整合 LLM 摘要。
- 智能体推荐反馈闭环作为重点维度，用户选择治理；设计随之调整。
- 后续范围原包含语义检索、用户自定义斜杠指令等方向，用户要求只保留 subagent、WebUI、远程部署、Docker 沙箱/部署，并为未授权后续功能增加开工门禁。

## 5. 反思

### 做得好的地方

- 一次只问一个问题，避免早期把所有细节一次性抛给用户。
- 设计分段确认，用户可以在架构、机制、工具、凭据、测试、范围等层面分别纠偏。
- 用户提出的技术栈和扩展需求没有被忽略，而是重新落到模块边界中。
- 在写 SPEC 前把“长期工具”和“课程硬性要求”都纳入考虑，避免只做一个 demo。

### 不满意的地方

- 设计过程中有些维度是在用户提醒后才补上，例如 session、`/skills`、工具崩溃隔离、LLM 摘要优先级。
- 讨论轮次较长，前期没有更早做一次“用户故事清单”来收敛范围。
- 第一版范围仍然偏大，后续执行时可能需要根据 TDD 和 subagent 流程进一步裁剪。

## 6. 冷启动自我验证

本节将在正式实现阶段执行并补充记录。

计划执行方式：

- 使用与主开发 agent 不同类型的新 session。
- 不导入本会话历史、memory 或额外口头解释。
- 只提供 `SPEC.md` 和 `PLAN.md`。
- 让冷启动 agent 自主选择 1-2 个 task 推进。
- 记录其暂停、提问、误读和产出差距。
- 根据结果修订 SPEC/PLAN，并在本文件记录修订前后差异。

当前状态：尚未执行，等待 Phase 0/1 有可实现的 task 后开始。

---

## 7. [claude code] 设计复查与补全记录

> 本节由 **Claude Code**（独立于主开发 agent 的复查会话）编写，时间：2026-08-03。
> 目的：在正式实现前，对照 `requirement_file/项目要求.md` 逐项核对 `SPEC.md` 与 `PLAN.md`，记录发现的问题、采取的修正与关键取舍。
> 本节之后的补充内容一律以 `[claude code]` 前缀标注，与原 Superpowers 流程产出区分。

### 7.1 复查方法

- 逐项核对需求文档 §1.1–§6.2 与 SPEC 的 11 项结构要求、PLAN 的 task 覆盖。
- 检查"SPEC 承诺的机制"与"PLAN 中是否有对应实现任务"是否一一对应。
- 检查任务间的数据流是否闭环（主循环 ↔ 治理 ↔ 反馈 ↔ 上下文 ↔ 日志 ↔ 审批）。

### 7.2 发现的问题

**总体结论：设计骨架合格（SPEC 结构完整覆盖需求 11 项、PLAN TDD 纪律好、治理维度拆解清晰），但 PLAN 的落地完整性不足——大量 SPEC 承诺的机制没有对应实现任务，尤其是"主循环串联治理/反馈/日志"这条项目立意的核心线。**

#### 重要缺口（直接影响硬性验收）

1. **凭据持久化未落地**：需求 §2.1 为必做项，SPEC §7.1 承诺"钥匙串 + 加密文件 fallback"，但 PLAN 只有 `InMemoryCredentialStore`（测试假实现），无 keyring/加密文件 backend 任务，`kl init`/`kl config key` 无法真正存 key → 验收标准 1 无法通过。
2. **内置工具大量占位未实现**：SPEC §3.5 承诺 17 个内置工具，PLAN 只实现 6 个；`apply_patch`（用户明确接受加入）、`run_command`、git 工具、`run_tests/run_lint/typecheck`、`delete_file`、`task_manage`（用户明确要求）只有目录占位 → 验收标准 3 无法通过。
3. **主循环与治理/反馈/上下文/日志未串联**：AgentLoop 只是"调 provider → 执行工具 → 循环"，Guardrail、Feedback、ContextAssembler、EventLogger 各自孤立，无集成任务 → 需求 §4.4 演示 ②、验收标准 4"反馈回灌"无法落地，这也是 harness 内核的立意缺失。
4. **审批/暂停/恢复链路未闭环**：`awaiting_approval`/`paused` 状态、`/pause`/`/continue`/`/abort`、审批面板都有，但 HITL→WS 通知→TUI 操作→结果回传→AgentLoop 恢复的中间链路无任务。
5. **daemon 认证未落地**：SPEC §4.2 承诺"随机本地 token"，但 API/CLI client 无认证实现。
6. **hook 只实现一半**：SPEC 承诺 `command` 与 `http` 两类，Task 4.5 只实现 `command`。

#### 次要遗漏

- 非 Git 工作区"更严格审批"无 `workspace_mode` 概念，未落地。
- `.env` 支持未提及（需求 §2.1 明确写了）。
- Session 的 provider/model 未持久化（sessions 表只有 3 列，与 SPEC §3.1 不符）。
- 工具超时未实现（SPEC §3.5 边界承诺）。
- MCP 只有 stub（`not connected`），是否算"可运行的最低实现"存疑。
- CLI 顶层命令（`kl init`/`kl run`/`kl server`）无实现任务。
- `feedback_demo` 深度不够：是"分类器演示"，非需求 §4.4 要求的"agent 收到失败后改变下一步"闭环演示。
- WebSocket 测试缺失（`test_ws.py` 只测 `/health`）。
- 小不一致：`kl config key show`（§7.1 有）未进 §3.10 命令列表；同步 `sqlite3` 在 async 环境下有阻塞风险。

### 7.3 采取的修正

**SPEC.md（3 处小修正）：**

- §3.10 补上 `kl config key show` 命令。
- §7.1 增加 `.env` 可选来源并说明明文风险。
- §3.9 明确 MCP 第一版实现 stdio 与 streamable-http 传输。

**PLAN.md（新增 13 个任务，全部按原 TDD 格式：失败测试 → 红 → 实现 → 绿 → commit）：**

| 任务 | 内容 | 对应缺口 |
|---|---|---|
| 1.10 | 凭据后端（keyring / 加密文件 / .env） | 缺口 1 |
| 1.11 | 补齐内置工具（shell/git/patch/validation/task_manage/delete_file） | 缺口 2 |
| 1.12 | ToolExecutor 超时与输出截断 | 次要 |
| 1.13 | 反馈回灌进 AgentLoop | 缺口 3 |
| 2.8 | Guardrail 集成进 ToolExecutor | 缺口 3 |
| 2.9 | 审计日志实时写入 AgentLoop | 缺口 3 |
| 2.10 | 非 Git 工作区更严格审批 | 次要 |
| 3.7 | daemon token 认证 | 缺口 5 |
| 3.8 | CLI 顶层命令（init/run/server） | 次要 |
| 3.9 | 审批 + 暂停/继续/中止端到端 | 缺口 4 |
| 4.8 | HTTP hook | 缺口 6 |
| 4.9 | MCP client 传输 | 次要 |
| 4.10 | ContextAssembler 接入 AgentLoop | 缺口 3 |

另修正：Task 1.7 sessions 表补 provider/model/status 字段；Task 5.1 `feedback_demo` 升级为闭环演示；目录结构、任务依赖、跟踪表同步更新。

### 7.4 关键取舍

1. **apply_patch 用纯 Python 最小 diff 应用器**，不用 `patch` 二进制 → Windows 下可测可用。
2. **审批链路用 `on_approval` 回调**驱动 AgentLoop 挂起/恢复，单测不依赖真实 WebSocket → 保持确定性可测；WS 只做广播与回传的接线。
3. **MCP 用官方 `mcp` SDK**，stdio 为单测覆盖路径，streamable-http 记为手动集成项。
4. **`Guardrail.check` 保持返回单字符串**，`action_id` 由 ToolExecutor 注册进 HITL → 不破坏既有 Task 2.5 测试。
5. **`AgentLoop` 新参数全部带默认值**（logger/context/on_approval）→ 向后兼容，既有 Task 1.9 测试不动。

### 7.5 反思

这次复查印证了 SPEC_PROCESS §5 中"第一版范围偏大"的判断：范围大导致 task 拆分时**漏掉了把零件装起来的集成任务**——SPEC 对机制的描述是完整的，但 PLAN 的任务列表里"模块各自存在"和"模块互相连通"是两回事，后者被忽略了。教训：writing-plans 阶段应额外做一遍"SPEC 承诺 → 实现任务"的双向矩阵核对，而不是只看模块内部设计。

---

## 8. [codex] 二次复查与补全记录

> 时间：2026-08-03
> 内容：在 Claude Code 补全后，对 `SPEC.md` 和 `PLAN.md` 再做一轮完整性复查。

### 8.1 发现的问题

1. **OpenAI 兼容 provider 缺失**：SPEC §3.4 要求第一版实现 OpenAI 兼容接口，但 PLAN 只有 `MockProvider` 和 provider 抽象，真实 LLM 路径无法运行。
2. **服务端 REST 路由缺失**：Task 3.8 的 CLI 依赖 `/api/v1/config/check`、`/api/v1/tasks` 等路由，但 Task 3.1 只实现 `/health`。
3. **`apply_patch` 可越界写文件**：工具从 patch 头解析目标路径，但治理只检查 `args["path"]`，导致补丁可写入工作区外。
4. **没有应用装配任务**：各模块分别可测，但没有任务把 config、provider、tool registry、guardrail、executor、logger、memory、context、API 组合成可运行服务。
5. **扩展模块没有接入主循环**：skill、hook、MCP、用户插件各自存在，但没有接线到 `AgentLoop` 或 `ToolRegistry`。
6. **插件工具接口与 `ToolRegistry` 不一致**：Task 4.7 只加载 `execute` 函数，而工具注册表要求 `Tool` 对象。

### 8.2 采取的修正

- 新增 Task 1.14：OpenAI-compatible provider、`load_app_config`、`build_provider_registry`。
- 新增 Task 3.10：session/task/provider/model/key 的 REST 路由。
- 新增 Task 4.11：hook、skill、MCP、用户插件接入 harness。
- 新增 Task 5.6：应用 bootstrap 和组件装配。
- 修正 Task 1.11：`apply_patch` 自行校验目标路径必须在工作区内。
- 修正 Task 4.7：插件必须导出 `TOOL` 对象，而不是裸 `execute` 函数。
- 统一 `create_app` 签名，保留 daemon token 认证参数。
- 更新任务依赖、仓库布局和任务跟踪表。

### 8.3 当前结论

复查后未再发现会阻止实现开始的结构性缺口。剩余风险主要是实现时的接口细节，例如 SQLite 同步调用、真实 keyring 可用性和 MCP streamable-http 的集成测试，这些应在对应 task 的验证阶段暴露并修正。

### 8.4 后续扩展性预留

用户要求 subagent 和 WebUI 在后续版本中具备扩展性。当前处理方式：

- 在 SPEC §12.3 增加“仅声明接口，不实现”的扩展性预留。
- subagent 预留为 `ToolRegistry` 中的受治理工具，并预留 `Task.parent_task_id`。
- WebUI 复用 `/api/v1` REST + WebSocket，TUI 不持有领域状态。
- 这些预留不改变开工门禁，未获用户允许前不进入 PLAN 实现任务。

---

## 9. [claude code][cold start check] Phase 0 执行记录（Task 0.1 / 0.2）

> 本节由 Claude Code 在正式实现会话中编写，时间：2026-08-03。
> 目的：记录 Phase 0 Bootstrap 的 Task 0.1（server 包骨架）与 Task 0.2（cli 包骨架）的执行过程、暂停提问点、SPEC/PLAN 暴露的缺陷与模糊点，供后续任务（0.3/0.4/1.x）参考。
> 关联提交：`7d4554d`（server 骨架）、`c45547b`（cli 骨架）；关联 PR：#1、#2（合回 `dev`）。

### 9.1 执行方式与结果

- 按开发要求执行：git worktree 隔离（每个独立模块一个 worktree 对应一个 PR）、subagent 驱动（每 task 派一个新鲜 implementer）、TDD 强制（红→绿→重构）、两阶段评审（先 spec 合规检查 → 再代码质量检查）、完成分支由 finishing-a-development-branch 决定。
- Task 0.1（server）：`pyproject.toml` + `kl_server/__init__.py`（`__version__="0.1.0"`）+ `tests/test_package.py`。红：`ModuleNotFoundError` → 绿：`1 passed`。
- Task 0.2（cli）：`package.json` + `tsconfig.json` + `src/main.ts`（`cliName()`）+ `test/main.test.ts`。红：`Cannot find module '../src/main'` → 绿：`1 passed`。
- 两 task 的 task 评审均 Spec ✅ + 质量 Approved，无 Critical/Important。整分支最终评审：Ready to merge = Yes，无 Critical。
- 环境：server 测试用 Python 3.11 venv（本机默认 `python` 为无 pip 的 msys2 3.14，见 §9.3 之 6）；cli 用 Node 22 / npm 10。

### 9.2 暂停提问点（用户裁决）

| # | 问题 | 用户裁决 |
|---|---|---|
| 1 | Task 0.1/0.2 是独立模块，worktree/PR 结构？ | 两个 worktree、两个 PR |
| 2 | worktree 分叉与 PR 目标分支？ | 从 `dev` 分叉，PR 合回 `dev` |
| 3 | origin/dev 落后本地 dev 5 个提交（缺 SPEC/PLAN 文档），PR 基准如何处理？ | 先推送 dev，再建 PR |

另有一处工具行为问题未打扰用户：`EnterWorktree` 的 `worktree.baseRef` 在会话启动后才写入 settings.json 未生效，默认从 origin/main 分叉；改用 `git worktree add <path> -b <branch> dev` 显式分叉解决。

### 9.3 SPEC/PLAN 暴露的缺陷与模糊点（含处理方式）

1. **PLAN Task 0.2 缺 `test` 脚本**：package.json 规格未列 scripts，但 Step 2 要求跑 `npm test` → 补充 `"scripts": {"test": "vitest run"}`。
2. **PLAN Task 0.1 测试命令的导入路径问题**：从仓库根 `python -m pytest server/tests/...` 无法导入 `kl_server`（包未安装）→ 先 `pip install -e "server[dev]"`（与后续 Task 0.3 Makefile 的安装命令一致）。
3. **PLAN Task 0.2 未给 tsconfig 内容** → 实现最小 strict 配置（ES2022/ESNext/bundler）。
4. **依赖版本全未固定**：server pyproject 按 brief 未固定版本；cli 依赖被 npm 写成 `"*"` 且 `package-lock.json` 未跟踪 → 当前**不可复现安装**；最终评审建议在 **Task 0.4 CI / phase-3 TUI 前**提交 lockfile 并改 caret 范围（风险最高项，需有意提交）。
5. **根 `.gitignore` 缺 Python 构建产物规则**（`__pycache__/`、`*.egg-info/`、`.pytest_cache/`）与 `node_modules/` → 每次 `make install`/`npm install` 后 `git status` 变脏，建议并入 **Task 0.3/0.4** PR。
6. **环境与 PLAN 字面命令不符**：本机默认 `python` 是 msys2 3.14.3 且无 pip/pytest，与 SPEC §8 的 3.11+ 不符 → 改用 Python 3.11 venv 执行测试命令（语义等价，非字面）。
7. **PLAN 未规定依赖锁定策略与 PR 模板**：spec §4.5 要求 CI pass 记录，但 lockfile 策略无约定；仓库无 PR 模板。
8. **cli tsconfig 未覆盖 test/**（`include:["src"]`）、无 `noEmit`/build 脚本；`"private": true` 为未规划但合理的添加——均为 minor，记录在案。

### 9.4 留给后续任务的已知事项（最终评审裁决：不阻塞本次合并）

- Task 0.3/0.4：根 `.gitignore` 补 `__pycache__/`、`*.egg-info/`、`.pytest_cache/`、`node_modules/`；Makefile 固化安装命令。
- Task 0.4 CI / phase-3 前：cli 依赖改 caret 范围并提交 `package-lock.json`。
- Task 5.3 分发前：server 依赖加下界/lockfile；补 `[tool.pytest.ini_options]`。

### 9.5 反思

本次执行再次验证 §5"第一版范围偏大"的判断：Phase 0 骨架就暴露了"PLAN 对可复现性/仓库卫生（依赖锁定、gitignore）约定不足"。后续任务应把"安装与构建产物可复现"作为 task 规格的一部分明确写进 PLAN，而不是靠 implementer 自行补充。

### 9.6 后续状态

- 远端 PR #1、#2 已由用户合并。
- 本地 `dev` 已 merge 远端结果，合并提交：`6bcd2a2`。
- 本地复验：server `1 passed`，cli `1 passed`。
- 已补 `AGENT_LOG.md`，并更新 PLAN Task 0.1/0.2 状态。
