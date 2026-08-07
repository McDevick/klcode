# KL Code SPEC 承诺兑现跟踪

> 对照 `SPEC.md` 逐节核验承诺、实现状态与缺口。证据为核验当日代码位置（file:line）。
> 状态标记：✅ 已实现 / ⚠️ 部分实现 / ❌ 缺口（未实现或与承诺行为相反）

---

## §3.1 Session 会话（核验 2026-08-07，兑现约 60%）

| 承诺 | 状态 | 证据 |
|---|---|---|
| `kl tui` 启动会话 | ✅ | cli/src/tui/app.tsx |
| `/sessions` 列出历史会话 | ✅ | routes.py:329 GET /sessions + tui/components/session-manager.tsx |
| `/session new/open/rename/close/delete` | ✅ | routes.py:483/506/523 + session-manager.tsx |
| session 持久化、跨 TUI 重启保留 | ✅ | core/session_manager.py（SQLite CRUD） |
| 持有工作区/供应商/模型/规则/记忆/任务历史 | ✅ | models/task.py:17-25；routes.py:483-504 可更新 rules |
| 一个 session 多个 task | ✅ | tasks.session_id 外键 |
| 删除 session 不删除共享项目记忆 | ✅ | routes.py:531-533 只清 session 级状态 |
| session id 不存在返回明确错误 | ✅ | routes.py:490/512/529 → 404 |
| 删除 session 必须二次确认 | ❌ | session-manager.tsx:106 直接删除，无确认 UI |
| 运行任务时 `/session close` 要求先暂停/中止 | ❌ | routes.py:506-521 直接置 closed，不检查任务状态 |
| 数据损坏时提示备份路径并阻止写入 | ✅ | database.py quick_check + API 503 detail 含 backup 路径 |

## §3.2 Task 任务（核验 2026-08-07，兑现约 55%）

| 承诺 | 状态 | 证据 |
|---|---|---|
| TUI 任务输入 / `kl run` / 可选工作区模式与分支 | ✅ | routes.py:43-54 CreateTaskPayload（workspace_mode/branch 校验） |
| 创建 task 记录 | ✅ | core/task_manager.py create |
| 7 态状态机（pending/running/awaiting_approval/paused/succeeded/failed/canceled） | ✅ | models/task.py:6-13；task_manager.py:109-126 状态流转校验 |
| 任务运行中暂停/继续/中止 | ✅ | routes.py:615-676；agent_loop.py:124/133 暂停门控；abort 取消协程 |
| 非 Git 工作区创建文件快照 | ✅ | routes.py:871-876 SnapshotManager |
| 同一 task 同一时间只有一个主循环 | ✅ | routes.py:592-596 409 防重复 run |
| 非 Git 模式默认更严格审批 | ✅ | guardrail.py:88/98 UNMANAGED_ESCALATION_TOOLS 升级审批 |
| 任务默认工作区范围内运行 | ✅ | guardrail ScopeFence |
| Git 工作区默认创建任务分支 | ❌ | 全库仅有 git_branch 内置工具，无任务自动建分支逻辑 |
| 分支创建失败回退非 Git 快照模式并提示 | ❌ | 无分支创建，自然无回退 |
| 非 Git 快照失败拒绝启动任务 | ❌（行为相反） | routes.py:877-878 明确"快照失败也不阻断任务执行" |
| 任务运行中可追加说明 | ✅ | POST /tasks/{id}/instructions + /note |
| 工作区不存在/不可写时创建失败给原因 | ✅ | create_task 校验 workspace 存在/目录/可写并返回 400 原因 |

## §3.3 AgentLoop 主循环（核验 2026-08-07，兑现约 80%）

| 承诺 | 状态 | 证据 |
|---|---|---|
| 每轮组织上下文、调用 LLM、解析动作或最终回答 | ✅ | agent_loop.py:161-313（ContextAssembler + 记忆 + 压缩） |
| 动作经注册→治理→沙箱→执行→反馈回下一轮 | ✅ | agent_loop.py:336-523 |
| 停止条件：任务完成/最大轮次/用户中止/致命错误 | ✅ | agent_loop.py:177 max_iterations；routes.py:615 abort；provider_error → FAILED |
| 停止条件：token 预算 | ❌ | 无循环级 token 上限；Task 模型无 token 用量字段（SPEC §6 承诺） |
| 每轮状态写入行为日志 | ✅ | llm_call/tool_result/feedback_generation 事件 |
| 不调用现成 agent 编排框架 | ✅ | 纯手写循环 |
| 工具崩溃不中断主循环 | ✅ | core/tool_executor.py:88-90 except Exception |
| 不允许无限循环：最大轮次 ✓ + token 预算 ✗ | ⚠️ | 仅 max_iterations 单保险 |
| provider 失败结构化错误进反馈闭环 | ✅ | agent_loop.py:259-288 provider_error 事件 + 记忆 |
| 连续失败达阈值任务失败并保留现场 | ❌（部分） | agent_loop.py:484-493 仅注入警告信号，不失败任务 |

## §3.4 ProviderRegistry 供应商（核验 2026-08-07，兑现约 85%）

| 承诺 | 状态 | 证据 |
|---|---|---|
| 多供应商、多模型配置 | ✅ | providers/factory.py:9-37 循环注册 config.providers |
| OpenAI 兼容接口 + 预留 Anthropic adapter | ✅ | providers/openai_compatible.py；base.py Protocol |
| 内置 MockProvider | ✅ | providers/registry.py:10 默认注册 mock |
| 供应商配置只保存 credential_ref，不保存 key | ⚠️（偏差） | config.py:18-19 允许 api_key 直写且 factory.py:16 优先使用；README 有本地场景说明，但与 SPEC 3.4/§7.1/4.2 冲突 |
| 模型列表输出 | ✅ | routes.py:814 GET /models、/config/model |
| 测试连接结果 | ⚠️（弱化） | cli config.ts:44-52 `provider test` 仅检查 provider 存在，不真实调用 LLM |
| 未配置 key 的付费供应商不可用 | ⚠️（行为粗暴） | factory.py:23-28 缺 key 直接 raise → 服务启动失败，而非"该供应商不可用" |
| 本地 provider 可无 key | ✅ | factory.py:16-22 无 key 也注册（api_key=None） |
| base URL 必须显式配置 | ✅ | config.py base_url 必填字段 |
| 配置不合法给出字段级错误 | ✅ | pydantic extra="forbid" + field_validator |
| 鉴权/限流/超时分别映射结构化错误 | ✅ | openai_compatible.py:49-54 APIStatusError（含 401/429）→ http error、APITimeoutError → provider timeout |

## §3.5 ToolRegistry 与 ToolExecutor 工具系统（核验 2026-08-07，兑现约 75%）

| 承诺 | 状态 | 证据 |
|---|---|---|
| 统一 Tool 接口：名称、参数 schema | ✅ | tools/base.py:17-23（name/description/schema/execute） |
| Tool 接口含权限声明、沙箱要求、超时 | ❌ | Protocol 无这些字段；治理/超时由 Guardrail/ToolExecutor 统一处理（"不能绕过治理"功能上成立） |
| 内置工具 17 个（SPEC 列表） | ✅（演进） | 16 个保留 + edit_file 新增；mcp_tool 由 MCP 远程工具注册替代（§3.9 机制） |
| 用户工具 `.kl/tools/<name>/` Python 插件 API | ✅ | plugins/loader.py |
| 工具描述进入系统提示词 | ✅（等价） | agent_loop.py:138-158 以原生 tools 参数提供，效果等价 |
| 工具执行有超时和资源限制 | ✅ | core/tool_executor.py:12-26（timeout=60s、max_output_chars=20k） |
| 大型输出截断并保留文件引用 | ⚠️ | 截断 ✓（truncated 标记）；文件引用 ✗（ToolResult 无引用字段） |
| 工具崩溃/超时/权限不足分别返回结构化错误 | ✅ | tool_executor.py:86-90 |
| schema 错误返回结构化错误 | ⚠️ | 无 harness 级 schema 校验层（registry.execute 直接执行，工具内部自校验） |

## §3.6 Guardrail 治理（核验 2026-08-07，兑现约 80%）

| 承诺 | 状态 | 证据 |
|---|---|---|
| ScopeFence 解析真实路径阻止越界 | ✅ | guardrail.py:17-33（resolve + parents + 空/NUL/drive 防护） |
| SandboxPolicy 命令白名单/黑名单 | ✅ | core/sandbox.py:59-93（含二进制混淆/未引用元字符防护，超出 SPEC） |
| SandboxPolicy 环境变量清理 | ❌ | sandbox.py 无 env 清理逻辑 |
| SandboxPolicy 超时和资源限制 | ⚠️ | 超时/截断在 ToolExecutor（非 SandboxPolicy 自身） |
| DangerClassifier 按动作/路径/命令/影响输出危险等级 | ✅ | guardrail.py:36-100（normal/dangerous/critical + rm -rf 根目标、git push --force 检测） |
| HITL 状态机：等待批准/拒绝/修改/超时 | ✅（缺超时） | guardrail.py:114-156（pending/approved/rejected/aborted 状态转移） |
| 审批超时按配置拒绝或冻结任务 | ❌ | HITLManager 无超时机制 |
| 非 Git 模式默认更严格 | ✅ | guardrail.py:88/98 UNMANAGED_ESCALATION_TOOLS |
| 治理逻辑不依赖 LLM | ✅ | 纯代码实现 |
| 每条决策写入行为日志 | ⚠️ | 决策经 tool_result 事件（error="rejected"）与 approval hooks 间接记录，无独立治理决策事件 |
| delete_file、危险 shell、越界写、发布类命令默认危险 | ✅ | DANGEROUS_TOOLS={delete_file, git_commit} + 命令内容检测 |
| 配置错误导致策略不可解析时默认拒绝执行 | ⚠️（语义差异） | 配置解析异常直接抛出（启动失败），无"默认拒绝"运行期路径 |

## §3.7 FeedbackSensors 反馈闭环（核验 2026-08-07，兑现约 95%）

| 承诺 | 状态 | 证据 |
|---|---|---|
| 解析分类：成功/测试失败/构建失败/lint/类型/超时/工具错误/provider 错误 | ✅ | models/feedback.py 9 类；feedback.py:59-131 分类器 |
| 生成结构化 Feedback 供下一轮使用 | ✅ | agent_loop.py:470-523 注入 history + 记忆 + 事件 |
| 反馈结果写入记忆和行为日志 | ✅ | agent_loop.py:500-520 memory.add + feedback_generation 事件 |
| 反馈分类不依赖 LLM | ✅ | 纯函数分类器 |
| 失败信息去重、截断、脱敏后回灌 | ✅ | feedback.py:39-56（香农熵脱敏 + 去重 + 末尾截断，本批增强） |
| 无法解析产物归类 unknown_error 并保留原始引用 | ✅ | feedback.py:108/123/125 + raw_ref（task_id:call.id） |

## §3.8 ContextAssembler 上下文、记忆与压缩（核验 2026-08-07，兑现约 85%）

| 承诺 | 状态 | 证据 |
|---|---|---|
| 每段上下文估算 token 用量，按模型预算分配 | ✅ | context.py:209-229 _fit_to_budget（二分截断） |
| 超预算时经 provider 生成结构化摘要 | ✅ | context.py:16-91 LLMSummarizer + 增量摘要（只摘要新增段） |
| 当前轮次、工具目录、规则默认不摘要 | ✅ | history[-1] 保留（177）；工具目录走 tools 参数（130-131）；规则在 base_sections（132） |
| 任务状态作为上下文输入 | ✅ | task_manage subtasks 注入 context 与压缩摘要 |
| 摘要写入记忆；原始内容保留日志 | ✅ | agent_loop.py:220-228 context_summary 写记忆；tool_result 事件保留原始 |
| 摘要失败时结构化 fallback 不崩溃 | ✅ | context.py:156-173/216-218 except → summary="" |
| token 计量和优先级规则可脱离 LLM 测试 | ✅ | token_estimator 注入 + 纯逻辑（test_context.py） |
| 记忆按需检索，不全量注入 | ✅ | memory.find(tags) + MEMORY_LIMIT=5（context.py:135-137） |
| 用户规则 > 项目规则 > 默认行为 | ✅ | .kl/rules.md + AGENTS.md + session.rules 分层注入 |
| fallback 后仍超预算丢弃低价值历史并记录 | ✅ | context.py 记录 dropping/truncating + context_compressed 事件 |

## §3.9 Skill、Hook、MCP 与用户工具（核验 2026-08-07，兑现约 90%）

| 承诺 | 状态 | 证据 |
|---|---|---|
| skill manifest + Markdown 按关键词加载 | ✅ | skills/loader.py:33-63（关键词匹配 SKILL.md） |
| hook 事件：任务开始/结束、动作前/后、反馈生成、审批请求/完成、错误、中止 | ✅ | agent_loop.py 各 hooks.run 调用点（task_start/task_end/action_before/action_after/feedback_generation/approval_request/approval_complete/error/abort） |
| hook 支持 command 和 http 两类 | ✅ | hooks/manager.py:86-93 |
| hook payload 自动脱敏 | ❌ | hooks/manager.py:123/137 直接透传 json.dumps(payload)，无脱敏 |
| hook 失败策略可配置：忽略或中止任务 | ✅ | hooks/manager.py:46-57 on_error="ignore"/"abort" |
| hook 超时按失败策略处理 | ✅ | subprocess/httpx timeout=30s → 异常按 on_error 处理 |
| MCP stdio + streamable-http 双传输，不可用返回结构化错误 | ✅ | mcp/transport.py、adapter.py（已复核） |
| 用户工具 Python 插件 API，与内置同等治理 | ✅ | plugins/loader.py + ToolExecutor 统一治理 |
| skill 只是内容，不替代 harness 机制 | ✅ | 仅注入上下文文本 |
| 用户工具默认受沙箱和审批约束 | ✅ | ToolExecutor 统一 guardrail 检查 |
| skill 加载失败忽略并记录 | ✅ | skills/loader.py:38-46/58-61 warning 忽略 |

## §3.10 CLI/TUI 与斜杠指令（核验 2026-08-07，兑现约 75%）

| 承诺 | 状态 | 证据 |
|---|---|---|
| `kl init` / `kl server start/stop/status` / `kl run` / `kl tui` | ✅ | cli/src/commands/init.ts、server.ts、run.ts；main.ts |
| `kl config provider add/list/test` | ✅（test 弱化见 §3.4） | cli/src/commands/config.ts:28-55 |
| `kl config key set/test/clear/show` | ✅ | config.ts:63-106 |
| TUI 斜杠指令 18 个（/config /provider /model /key /tools /hooks /skills /mcp /sessions /session 系列 /pause /continue /abort /status /help /exit） | ⚠️（15 个，缺 5 个） | app.tsx:18-33 实际 15 个：/session /skills /mcp /config /status /model /context /compact /help /abort /pause /continue /debug /mouse /exit；缺 /provider /key /tools /hooks /sessions（/session 面板替代） |
| 指令经 CommandRegistry 注册（名称/别名/参数 schema/适用状态/说明/处理器） | ⚠️（简化） | 实现为 SLASH_COMMANDS 数组 + if 链（app.tsx:566-731），无参数 schema/适用状态机制 |
| /help 自动从注册表生成 | ✅ | app.tsx:570-572 map 生成 |
| 配置向导：供应商/模型/base URL/key 隐藏输入 | ✅ | tui/components/config-wizard.tsx |
| 实时任务视图、审批面板、会话恢复 | ✅ | messages.tsx、approval.tsx、session-manager.tsx |
| 运行中指令和空闲指令分开限制 | ⚠️ | /abort//pause//continue 有任务存在门控（app.tsx:705-709）；其余指令无状态门控 |
| /exit 在任务运行时先确认 | ❌ | app.tsx:567-569 直接 process.exit(0)，无运行中检查 |
| 未知指令给出帮助提示 | ✅ | app.tsx:730 "未知命令" |
| 参数错误显示该指令 schema | ❌ | 无 schema 机制（同 CommandRegistry 缺口） |
| 超出 SPEC 的增强（不扣分） | — | /context /compact /debug /mouse、config tools 命令 |

## §3.11 行为日志与审计（核验 2026-08-07，兑现约 85%）

| 承诺 | 状态 | 证据 |
|---|---|---|
| 任务/动作/反馈/摘要事件写入 append-only 结构化日志 | ✅ | event_logger.py:18-38（"a" 模式 + flush）；loop_start/llm_call/tool_result/feedback_generation 等事件 |
| 治理决策事件 | ⚠️ | 决策经 tool_result（error="rejected"）间接记录，无独立治理事件（同 §3.6） |
| 审批/人工干预事件 | ⚠️ | approval_request/approval_complete 走 hooks 通道，EventLogger 仅 loop_end(reason=needs_approval) 间接体现 |
| AGENT_LOG 实时记录（不做完补写） | ✅ | 事件实时 write；AGENT_LOG.md 由开发流程维护 |
| 凭据、key、敏感环境变量自动脱敏 | ✅ | event_logger.py:46-57（key 名匹配 + 值正则 + command/env/credential_ref 字段全 REDACTED） |
| 日志支持按 task/session 回放 | ✅ | routes.py:379-446 history/feedback/context 端点 |
| 日志不保存明文凭据、不覆盖历史 | ✅ | 脱敏 + append-only |
| 日志写入失败时任务停止并提示 | ✅ | write 抛 RuntimeError → 主循环异常 → task FAILED + 错误事件广播 |

## §4 非功能需求（核验 2026-08-07，兑现约 80%）

| 承诺 | 状态 | 证据 |
|---|---|---|
| daemon 仅监听 127.0.0.1 | ✅ | main.py:30-31（host=127.0.0.1, port=8700） |
| TUI 事件延迟秒级可见 | ✅ | WebSocket 事件流推送（ws.py + task_events.py） |
| 上下文 token 预算 | ✅ | §3.8 |
| 工具执行超时、重试上限、资源限制 | ⚠️ | 超时 60s + 输出截断 ✓（tool_executor.py）；重试上限 ✗（工具层无重试） |
| key 优先系统钥匙串 | ✅ | config/credentials.py:36-48（keyring → 加密文件 AESGCM → 内存回退） |
| 日志/hook payload/工具输出统一脱敏 | ⚠️ | 日志与工具输出进反馈 ✓；hook payload ✗（§3.9） |
| daemon 随机本地 token | ✅ | core/auth.py + app.py:87-94 middleware Bearer 校验 |
| ScopeFence/SandboxPolicy 代码层强制 | ✅ | §3.6 |
| 用户工具/MCP/hook 显式配置并标记信任边界 | ✅ | .kl/ 配置 + README 安全边界章节 |
| 远程化 TLS/认证/密钥轮换 | ✅（不实现） | §12 未授权范围，不实现合理 |
| make test 一键 | ✅ | Makefile |
| kl init 覆盖全新机器冷启动 | ⚠️ | README 已知限制：kl init 依赖 daemon 已运行（冷启动流程有 gap） |
| 首次配置 CLI/TUI 引导 | ✅ | config-wizard.tsx + config 命令 |
| 日志覆盖任务/动作/治理/反馈/审批/摘要/hook/人工干预 | ⚠️ | 审批与治理决策事件缺口（§3.6/§3.11） |
| 日志可回放 | ✅ | §3.11 |
| 状态接口：session/task/上下文预算 | ✅ | /status、/sessions、/context |
| 状态接口：token 用量 | ❌ | Task 模型无 token 用量字段（同 §3.3） |
| GitHub Actions unit-test job | ✅ | .github/workflows/ci.yml（push+PR、make ci+test） |
| .gitlab-ci.yml unit-test job | ✅ | 根目录 .gitlab-ci.yml（python:3.11 + node 22） |
| 分发阶段构建检查和产物检查 | ❌ | ci.yml 仅测试，无构建/产物检查步骤 |
| 最终交付前 CI pass | ✅（本地） | 本地 444+96 passed；远程 CI 状态未验证 |
| AGENT_LOG.md 实时维护 | ✅（存在性） | AGENT_LOG.md 84KB 持续维护；"实时记录不补写"规则未从内容深核 |

## §6 数据模型（核验 2026-08-07，兑现约 70%）

| 承诺 | 状态 | 证据 |
|---|---|---|
| Session：id/名称/工作区/provider/model/规则/状态/时间戳 | ✅ | models/task.py:17-25 |
| Task：id/session_id/描述/状态/模式/分支或快照/摘要/时间戳 | ✅ | models/task.py:29-38 |
| Task 含 token 用量、预留 parent_task_id | ❌ | 两字段均缺（subagent 预留未落实） |
| Action 含治理结果/沙箱结果/审批状态/执行结果 | ❌ | models/action.py:5-12 仅基础字段；结果在 ToolResult/执行链路 |
| Approval：id/action_id/危险等级/原因/结果/用户备注 | ⚠️ | guardrail.py:106-111 ApprovalRequest 仅 action_id/tool/command/state |
| Feedback：id/task_id/action_id/类别/摘要/原始输出引用 | ⚠️ | raw_ref 折叠 task_id:call.id（§3.7 已记录） |
| MemoryEntry：id/scope/类型/标签/内容/token 估算/时间戳 | ⚠️ | store.py add(scope/kind/tags/content)；token 估算字段缺 |
| EventLog：id/task_id/事件类型/脱敏 payload/时间戳 | ✅ | event_logger.py |
| WorkspaceSnapshot：路径/校验值 | ⚠️ | snapshot.py 有路径 + .meta；校验值缺 |
| SQLite 存状态/任务/记忆/审计索引 | ✅ | storage/database.py + memory/store.py |
| 大型输出存文件，库只存引用和摘要 | ⚠️ | 输出截断后进日志/记忆，无独立输出文件存储 |
| 项目数据 .kl/ 并 gitignore | ✅ | .gitignore + README |
| 凭据不进 SQLite 或日志 | ✅ | credentials.master 独立加密文件 |

## §7 凭据与分发（核验 2026-08-07，兑现约 85%）

| 承诺 | 状态 | 证据 |
|---|---|---|
| kl init 隐藏输入录入 key | ✅ | cli/src/commands/init.ts |
| key 优先钥匙串（Win Credential Manager/macOS Keychain/Linux Secret Service） | ✅ | config/backends.py KeyringBackend |
| 钥匙串不可用 → 带主密码加密文件并说明风险 | ✅ | EncryptedFileBackend（AESGCM）+ 初始化提示 |
| .env 可选来源并说明明文风险 | ✅ | README + credentials 支持 |
| 配置文件只保存 credential_ref | ⚠️（偏差） | config.yaml 允许直写 api_key（§3.4 已记录） |
| kl config key set/test/clear/show | ✅ | config.ts:63-106 |
| key show 只显示是否已配置 | ✅ | routes.py:843-848 返回 {"configured": bool} |
| 服务端 PyPI/uv 安装（console 入口 kl-server） | ✅ | pyproject.toml |
| CLI/TUI npm 安装（bin 配置） | ✅ | cli/package.json |
| make dev 同时启动服务端和 TUI | ❌ | README 已知限制：make dev 为占位守卫（退出码 1） |
| Docker 作为后续部署方案 | ✅（不实现） | §12 未授权范围 |

## §9 验收标准（核验 2026-08-07，兑现 8/9 条基本满足）

| 承诺 | 状态 | 备注 |
|---|---|---|
| 1. 全新机器安装 + kl init，key 不进入源码日志 | ⚠️ | 安装配置就绪；kl init 依赖 daemon 先行（gap 同 §4.3） |
| 2. TUI 提交/实时观察/审批/暂停继续中止/会话恢复/斜杠指令 | ✅ | 核心功能在（指令数量差异见 §3.10） |
| 3. 内置工具齐全 + 插件注册通过治理 | ✅ | §3.5 |
| 4. mock-LLM 单测覆盖 5 类机制 | ✅ | test_guardrail/test_feedback/test_agent_loop 等 |
| 5. 上下文 token 预算，mock 验证摘要和 fallback | ✅ | test_context.py |
| 6. 行为日志覆盖关键事件且无明文 key | ✅ | §3.11（审批/治理事件缺口见 §3.6） |
| 7. make test 一键通过 + 双 CI unit-test | ✅ | 本地 444+96 passed；ci.yml/.gitlab-ci.yml 均含 unit-test |
| 8. examples/ mock-LLM 机制演示 | ✅ | 4 个演示脚本（guardrail/feedback/context/tool_error） |
| 9. 文档齐全 | ✅ | SPEC/PLAN/SPEC_PROCESS/AGENT_LOG/REFLECTION/README |

## 核对记录

- 2026-08-07：§3.1–3.3 核对完成。总体：核心机制（状态机/暂停/中止/快照/主循环/日志）兑现扎实；缺口集中在错误处理承诺（快照失败拒绝启动、连续失败失败任务、token 预算停止条件）与 Git 自动化（自动建分支/回退）、交互边界（删除确认/close 检查/追加说明/workspace 校验）。
- 2026-08-07：§3.4–3.6 核对完成。总体：治理层（ScopeFence/DangerClassifier/HITL）与 Provider 层兑现度高；缺口集中在工具声明字段（权限/沙箱/超时）、SandboxPolicy 环境变量清理、审批超时、schema 校验层；两处 SPEC 明确冲突的偏差：config.yaml 允许直写 api_key、缺 key 时服务整体启动失败。
- 2026-08-07：§3.7–3.9 核对完成。反馈闭环（3.7）兑现度最高（本批已增强熵脱敏与重试预算）；3.8 缺口：任务状态未进上下文、规则分层合并未实现、丢弃记录缺失；3.9 缺口：hook payload 未脱敏（SPEC 明列，与审计日志的脱敏形成不对称）。
- 2026-08-07：§3.10–3.11 核对完成。CLI 命令全覆盖；TUI 斜杠指令 15/18（缺 /provider /key /tools /hooks /sessions），/exit 无运行中确认，CommandRegistry 简化为数组+if 链；审计日志核心承诺（append-only/脱敏/回放/写失败停任务）全部兑现，缺口为审批与治理决策无独立事件。
- 2026-08-07：§4/§6/§7/§9 核对完成。安全硬承诺（127.0.0.1/token/钥匙串/ScopeFence）全部兑现；数据模型 8 实体中 Session/EventLog/WorkspaceSnapshot 部分完整，Task 缺 token 用量与 parent_task_id；分发就绪但 make dev 为占位守卫、CI 无构建/产物检查；验收标准 9 条基本满足（kl init 冷启动 gap 为唯一 ⚠️）。

## 全量缺口汇总（按修复优先级）

**P0（行为与承诺相反 / 安全）**
1. 非 Git 快照失败时任务照常执行（§3.2，应拒绝启动）
2. config.yaml 允许直写 api_key（§3.4/§7.1/§4.2 冲突）
3. hook payload 未脱敏（§3.9，外发通道无脱敏）

**P1（SPEC 明列缺失）**
4. Git 任务自动建分支 + 失败回退快照（§3.2）
5. 连续失败达阈值任务失败保留现场（§3.3，现有仅警告）
6. 循环级 token 预算停止条件（§3.3/§4.4）
7. 审批超时机制（§3.6）
8. SandboxPolicy 环境变量清理（§3.6）
9. 任务运行中追加说明（§3.2）
10. 任务状态进上下文（§3.8）
11. 规则分层合并（§3.8）
12. /exit 运行中确认、删除二次确认、/session close 运行中检查（§3.1/§3.10）
13. 工具声明字段（权限/沙箱/超时）（§3.5）
14. 缺 key 时单个供应商不可用而非整体启动失败（§3.4）

**P2（规格形式/增强）**
15. CommandRegistry 机制（§3.10，现为数组+if 链）
16. 5 个斜杠指令缺失（§3.10）
17. 审批/治理决策独立日志事件（§3.6/§3.11）
18. 数据模型字段补齐（token 用量/parent_task_id/Action 结果字段/快照校验值等）（§6）
19. 大输出独立文件存储（§6）
20. CI 分发构建检查（§4.5）、make dev 接线（§7.2）、kl init 冷启动 gap（§4.3）
21. schema 校验层（§3.5）、文件引用（§3.5）、provider test 真实连接（§3.4）
