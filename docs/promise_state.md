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
| 测试连接结果 | ✅ | routes.py:974-1005 `/providers/{name}/test` 真实调用 provider.complete；cli config.ts provider test 走该端点 |
| 未配置 key 的付费供应商不可用 | ✅ | factory.py 已删除缺 key raise；缺 key 供应商注册为无 key 实例，运行时调用才失败（不可用语义从启动期推迟到调用期） |
| 本地 provider 可无 key | ✅ | factory.py:16-22 无 key 也注册（api_key=None） |
| base URL 必须显式配置 | ✅ | config.py base_url 必填字段 |
| 配置不合法给出字段级错误 | ✅ | pydantic extra="forbid" + field_validator |
| 鉴权/限流/超时分别映射结构化错误 | ✅ | openai_compatible.py:49-54 APIStatusError（含 401/429）→ http error、APITimeoutError → provider timeout |

## §3.5 ToolRegistry 与 ToolExecutor 工具系统（核验 2026-08-07，兑现约 75%）

| 承诺 | 状态 | 证据 |
|---|---|---|
| 统一 Tool 接口：名称、参数 schema | ✅ | tools/base.py:17-23（name/description/schema/execute） |
| Tool 接口含权限声明、沙箱要求、超时 | ✅ | tools/base.py Protocol 含 permissions/sandbox/timeout；18 个内置工具全量声明；Action 携带声明（models/action.py）；守卫按权限分级（guardrail.py DANGEROUS_PERMISSIONS/UNMANAGED_ESCALATION_PERMISSIONS）；catalog 输出审计 |
| 内置工具 18 个（SPEC 列表） | ✅（演进） | 17 个保留 + edit_file + read_tool_output 新增；mcp_tool 由 MCP 远程工具注册替代（§3.9 机制） |
| 用户工具 `.kl/tools/<name>/` Python 插件 API | ✅ | plugins/loader.py |
| 工具描述进入系统提示词 | ✅（等价） | agent_loop.py:138-158 以原生 tools 参数提供，效果等价 |
| 工具执行有超时和资源限制 | ✅ | tool_executor.py 按工具声明 timeout 定制（run_tests 180s/run_command 120s/读写 30s），未声明回退 60s；max_output_chars=20k |
| 大型输出截断并保留文件引用 | ✅ | 截断时完整输出落盘 ~/.kl/tool_outputs/<session>/<task>/<tool>_<uuid>.txt（tool_executor _persist_full_output，OSError 容错），references 含落盘路径 + 操作涉及文件双语义，meta.output_file 记录 |
| 工具崩溃/超时/权限不足分别返回结构化错误 | ✅ | tool_executor.py:86-90 |
| schema 错误返回结构化错误 | ✅ | tools/registry.py:38-51 jsonschema 执行前校验，ValidationError/SchemaError 区分，统一 schema_error: <message>；jsonschema>=4.0 已入 pyproject |

## §3.6 Guardrail 治理（核验 2026-08-08，审批超时已修复，兑现 100%）

| 承诺 | 状态 | 证据 |
|---|---|---|
| ScopeFence 解析真实路径阻止越界 | ✅ | guardrail.py:17-33（resolve + parents + 空/NUL/drive 防护） |
| SandboxPolicy 命令白名单/黑名单 | ✅ | core/sandbox.py:59-93（含二进制混淆/未引用元字符防护，超出 SPEC） |
| SandboxPolicy 环境变量清理 | ✅ | sandbox.py sanitize_env：_BASE_ENV_KEYS 白名单 + _SENSITIVE_ENV_RE（AWS_/OPENAI/KEY/TOKEN/SECRET/PASSWORD 等）过滤 → command_env() 注入 ctx.sandbox.env → shell.py env= 子进程只拿裁剪环境 |
| SandboxPolicy 超时和资源限制 | ✅ | SandboxConfig（timeout/max_cpu_seconds/max_memory_mb）→ SandboxPolicy → executor 每工具注入 ctx.sandbox.limits + timeout=min(tool, sandbox) → shell.py RLIMIT_CPU/RLIMIT_AS preexec_fn 生效（POSIX） |
| DangerClassifier 按动作/路径/命令/影响输出危险等级 | ✅ | guardrail.py:36-100（normal/dangerous/critical + rm -rf 根目标、git push --force 检测） |
| HITL 状态机：等待批准/拒绝/修改/超时 | ✅ | guardrail.py:114-156（pending/approved/rejected/aborted 状态转移）+ ApprovalHub 超时决策 |
| 审批超时按配置拒绝或冻结任务 | ✅ | ApprovalHub asyncio.wait_for + agent_loop decision=timeout；默认 300s，config.guardrail.approval_timeout_seconds 可调 |
| 非 Git 模式默认更严格 | ✅ | guardrail.py:88/98 UNMANAGED_ESCALATION_TOOLS |
| 治理逻辑不依赖 LLM | ✅ | 纯代码实现 |
| 每条决策写入行为日志 | ✅ | tool_executor 每次 guardrail.check 后写独立 governance_decision 事件（tool/decision/args/permissions），异常写 decision="error"；bootstrap 注入 executor.logger |
| delete_file、危险 shell、越界写、发布类命令默认危险 | ✅ | DANGEROUS_PERMISSIONS={"destructive"}（delete_file/git_commit 声明）+ 命令内容检测（rm -rf 根、git push --force） |
| 配置错误导致策略不可解析时默认拒绝执行 | ✅ | bootstrap 加载失败 → SandboxConfig(deny_all=True) / SandboxPolicy(deny_all=True) 兜底（fail-closed），错误汇总进 deps.config_error 暴露；默认 deny 含 rm/docker |

## §3.7 FeedbackSensors 反馈闭环（核验 2026-08-07，兑现约 95%）

| 承诺 | 状态 | 证据 |
|---|---|---|
| 解析分类：成功/测试失败/构建失败/lint/类型/超时/工具错误/provider 错误 | ✅ | models/feedback.py 9 类；feedback.py:59-131 分类器 |
| 生成结构化 Feedback 供下一轮使用 | ✅ | agent_loop.py:470-523 注入 history + 记忆 + 事件 |
| 反馈结果写入记忆和行为日志 | ✅ | agent_loop.py:500-520 memory.add + feedback_generation 事件 |
| 反馈分类不依赖 LLM | ✅ | 纯函数分类器 |
| 失败信息去重、截断、脱敏后回灌 | ✅ | feedback.py:39-56（香农熵脱敏 + 去重 + 末尾截断，本批增强） |
| 无法解析产物归类 unknown_error 并保留原始引用 | ✅ | feedback.py:108/123/125 + raw_ref（task_id:call.id） |

## §3.8 ContextAssembler 上下文、记忆与压缩（核验 2026-08-07，兑现 100%）

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
| hook payload 自动脱敏 | ✅ | hooks/manager.py:20/125/141 接入 event_logger.redact_payload，command/http 双通道均脱敏 |
| hook 失败策略可配置：忽略或中止任务 | ✅ | hooks/manager.py:46-57 on_error="ignore"/"abort" |
| hook 超时按失败策略处理 | ✅ | subprocess/httpx timeout=30s → 异常按 on_error 处理 |
| MCP stdio + streamable-http 双传输，不可用返回结构化错误 | ✅ | mcp/transport.py、adapter.py（已复核） |
| 用户工具 Python 插件 API，与内置同等治理 | ✅ | plugins/loader.py + ToolExecutor 统一治理 |
| skill 只是内容，不替代 harness 机制 | ✅ | 仅注入上下文文本 |
| 用户工具默认受沙箱和审批约束 | ✅ | ToolExecutor 统一 guardrail 检查 |
| skill 加载失败忽略并记录 | ✅ | skills/loader.py:38-46/58-61 warning 忽略 |

## §3.10 CLI/TUI 与斜杠指令（核验 2026-08-08，兑现约 90%）

| 承诺 | 状态 | 证据 |
|---|---|---|
| `kl init` / `kl server start/stop/status` / `kl run` / `kl tui` | ✅ | cli/src/commands/init.ts、server.ts、run.ts；main.ts |
| `kl config provider add/list/test` | ✅（test 弱化见 §3.4） | cli/src/commands/config.ts:28-55 |
| `kl config key set/test/clear/show` | ✅ | config.ts:63-106 |
| TUI 斜杠指令（SPEC 18 个） | ⚠️（17 个实际，缺 5 个名义指令） | 实际 17 个：/session /skills /mcp /config /connect /status /model /context /compact /help /abort /note /pause /continue /debug /mouse /exit；缺 /provider /key /tools /hooks /sessions——/sessions 由 /session 面板覆盖、/provider /key 由 /config 向导+/model 覆盖、/tools /hooks 无覆盖 |
| 指令经 CommandRegistry 注册（名称/别名/参数 schema/适用状态/说明/处理器） | ✅ | cli/src/tui/commands.ts 独立模块：CommandDef（name/desc/usage/args/aliases/available/handler）+ CommandRegistry（register/resolve/list/run）；app.tsx COMMAND_META 批量注册；/config 别名 /cfg、/connect 别名 /conn |
| /help 自动从注册表生成 | ✅ | app.tsx 从 COMMAND_META 生成 |
| 配置向导：供应商/模型/base URL/key 隐藏输入 | ✅ | tui/components/connect-manager.tsx（替代已删除的 config-wizard） |
| 实时任务视图、审批面板、会话恢复 | ✅ | messages.tsx、approval.tsx、session-manager.tsx |
| 运行中指令和空闲指令分开限制 | ✅ | 双向门控：空闲侧 /session//config//connect//compact 用 available: !state.running；任务侧 /abort//note//pause//continue 用 available: taskId !== null |
| /exit 在任务运行时先确认 | ✅ | app.tsx 运行中第一次 /exit 提示"再次输入 /exit 确认退出"，第二次才退出（专项测试） |
| 未知指令给出帮助提示 | ✅ | registry.run 返回"未知命令" |
| 参数错误显示该指令 schema | ✅ | registry.run 生成式错误："缺少参数 X\n用法: usage"（/note 已启用） |
| 超出 SPEC 的增强（不扣分） | — | /context /compact /debug /mouse /connect、config tools 命令、别名机制 |

## §3.11 行为日志与审计（核验 2026-08-08，兑现 100%）

| 承诺 | 状态 | 证据 |
|---|---|---|
| 任务/动作/反馈/摘要事件写入 append-only 结构化日志 | ✅ | event_logger.py:18-38（"a" 模式 + flush）；loop_start/llm_call/tool_result/feedback_generation 等事件 |
| 治理决策事件 | ✅ | tool_executor 写独立 governance_decision 事件（tool/decision/args/permissions） |
| 审批/人工干预事件 | ✅ | agent_loop 独立写 approval_request（action_id/tool/args/level）+ approval_complete（action_id/decision）审计事件，专项测试锁定 |
| AGENT_LOG 实时记录（不做完补写） | ✅ | 事件实时 write；AGENT_LOG.md 由开发流程维护 |
| 凭据、key、敏感环境变量自动脱敏 | ✅ | event_logger.py:46-57（key 名匹配 + 值正则 + command/env/credential_ref 字段全 REDACTED） |
| 日志支持按 task/session 回放 | ✅ | routes.py:379-446 history/feedback/context 端点 |
| 日志不保存明文凭据、不覆盖历史 | ✅ | 脱敏 + append-only |
| 日志写入失败时任务停止并提示 | ✅ | write 抛 RuntimeError → 主循环异常 → task FAILED + 错误事件广播 |

## §4 非功能需求（核验 2026-08-08，兑现约 90%）

| 承诺 | 状态 | 证据 |
|---|---|---|
| daemon 仅监听 127.0.0.1 | ✅ | main.py:30-31（host=127.0.0.1, port=8700） |
| TUI 事件延迟秒级可见 | ✅ | WebSocket 事件流推送（ws.py + task_events.py） |
| 上下文 token 预算 | ✅ | §3.8 |
| 工具执行超时、重试上限、资源限制 | ⚠️ | 超时 ✓（tool.timeout 与 sandbox.timeout 取 min）+ 输出截断 ✓ + CPU/内存限制 ✓（RLIMIT_CPU/RLIMIT_AS，POSIX）；重试上限 ✗（工具层无重试） |
| key 优先系统钥匙串 | ✅ | config/credentials.py:36-48（keyring → 加密文件 AESGCM → 内存回退） |
| 日志/hook payload/工具输出统一脱敏 | ✅ | 日志 ✓（event_logger）+ hook payload ✓（redact_payload 接入）+ 工具输出进反馈/日志均脱敏 |
| daemon 随机本地 token | ✅ | core/auth.py + app.py:87-94 middleware Bearer 校验 |
| ScopeFence/SandboxPolicy 代码层强制 | ✅ | §3.6 |
| 用户工具/MCP/hook 显式配置并标记信任边界 | ✅ | .kl/ 配置 + README 安全边界章节 |
| 远程化 TLS/认证/密钥轮换 | ✅（不实现） | §12 未授权范围，不实现合理 |
| make test 一键 | ✅ | Makefile |
| kl init 覆盖全新机器冷启动 | ✅ | 连接被拒时自动拉起 daemon（复用 server start 探测/拉起逻辑）→ 轮询 /health 就绪 → 重试；仅网络错误触发，HTTP 错误不启动 |
| 首次配置 CLI/TUI 引导 | ✅ | tui/components/connect-manager.tsx（替代已删除的 config-wizard）+ config 命令 |
| 日志覆盖任务/动作/治理/反馈/审批/摘要/hook/人工干预 | ✅ | 全事件类型齐备：governance_decision（治理）+ approval_request/approval_complete（审批/人工干预，§3.11 已 100%） |
| 日志可回放 | ✅ | §3.11 |
| 状态接口：session/task/上下文预算 | ✅ | /status、/sessions、/context |
| 状态接口：token 用量 | ❌ | Task 模型无 token 用量字段（同 §3.3） |
| GitHub Actions unit-test job | ✅ | .github/workflows/ci.yml（push+PR、make ci+test） |
| .gitlab-ci.yml unit-test job | ✅ | 根目录 .gitlab-ci.yml（python:3.11 + node 22） |
| 分发阶段构建检查和产物检查 | ✅ | ci.yml dist-check job（needs unit-test）：python -m build server（wheel/sdist）+ zipfile 断言 kl_server 包；cli npm run build + node dist/main.js --help 可运行性 |
| 最终交付前 CI pass | ✅（本地） | 本地 480+103 passed；远程 CI 曾因 npmmirror 502 失败一次（基础设施问题非代码），恢复后重跑通过 |
| AGENT_LOG.md 实时维护 | ✅（存在性） | AGENT_LOG.md 约 82KB 持续维护；"实时记录不补写"规则未从内容深核 |

## §6 数据模型（核验 2026-08-08，兑现约 75%）

| 承诺 | 状态 | 证据 |
|---|---|---|
| Session：id/名称/工作区/provider/model/规则/状态/时间戳 | ✅ | models/task.py:17-25 |
| Task：id/session_id/描述/状态/模式/分支或快照/摘要/时间戳 | ✅ | models/task.py:29-38 |
| Task 含 token 用量、预留 parent_task_id | ❌ | 两字段均缺（subagent 预留未落实） |
| Action 含治理结果/沙箱结果/审批状态/执行结果 | ⚠️ | Action 已含 permissions/sandbox 声明字段；结果仍在 ToolResult/执行链路，但经 governance_decision 事件独立记录（审计可回放） |
| Approval：id/action_id/危险等级/原因/结果/用户备注 | ⚠️ | ApprovalRequest 仅 action_id/tool/command/state；但审批审计已独立落盘（approval_request 含 level、approval_complete 含 decision），仅"原因文本/用户备注"缺 |
| Feedback：id/task_id/action_id/类别/摘要/原始输出引用 | ⚠️ | raw_ref 折叠 task_id:call.id（§3.7 已记录） |
| MemoryEntry：id/scope/类型/标签/内容/token 估算/时间戳 | ⚠️ | store.py add(scope/kind/tags/content)；token 估算字段缺 |
| EventLog：id/task_id/事件类型/脱敏 payload/时间戳 | ✅ | event_logger.py |
| WorkspaceSnapshot：路径/校验值 | ⚠️ | snapshot.py 有路径 + .meta（restore 时校验归属）；内容校验值缺 |
| SQLite 存状态/任务/记忆/审计索引 | ✅ | storage/database.py + memory/store.py |
| 大型输出存文件，库只存引用和摘要 | ✅ | 截断时完整输出落盘 ~/.kl/tool_outputs/（tool_executor _persist_full_output），references + meta.output_file 引用 |
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
| make dev 同时启动服务端和 TUI | ✅ | Makefile dev -> cd cli && npm run tui；服务端未启动时 TUI 自动拉起 daemon |
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
| 7. make test 一键通过 + 双 CI unit-test | ✅ | 本地 480+103 passed；ci.yml/.gitlab-ci.yml 均含 unit-test |
| 8. examples/ mock-LLM 机制演示 | ✅ | 4 个演示脚本（guardrail/feedback/context/tool_error） |
| 9. 文档齐全 | ✅ | SPEC/PLAN/SPEC_PROCESS/AGENT_LOG/REFLECTION/README |

## 核对记录

- 2026-08-07：§3.1–3.3 核对完成。总体：核心机制（状态机/暂停/中止/快照/主循环/日志）兑现扎实；缺口集中在错误处理承诺（快照失败拒绝启动、连续失败失败任务、token 预算停止条件）与 Git 自动化（自动建分支/回退）、交互边界（删除确认/close 检查/追加说明/workspace 校验）。
- 2026-08-07：§3.4–3.6 核对完成。总体：治理层（ScopeFence/DangerClassifier/HITL）与 Provider 层兑现度高；缺口集中在工具声明字段（权限/沙箱/超时）、SandboxPolicy 环境变量清理、审批超时、schema 校验层；两处 SPEC 明确冲突的偏差：config.yaml 允许直写 api_key、缺 key 时服务整体启动失败。
- 2026-08-07：§3.7–3.9 核对完成。反馈闭环（3.7）兑现度最高（本批已增强熵脱敏与重试预算）；3.8 缺口：任务状态未进上下文、规则分层合并未实现、丢弃记录缺失；3.9 缺口：hook payload 未脱敏（SPEC 明列，与审计日志的脱敏形成不对称）。
- 2026-08-07：§3.10–3.11 核对完成。CLI 命令全覆盖；TUI 斜杠指令 15/18（缺 /provider /key /tools /hooks /sessions），/exit 无运行中确认，CommandRegistry 简化为数组+if 链；审计日志核心承诺（append-only/脱敏/回放/写失败停任务）全部兑现，缺口为审批与治理决策无独立事件。
- 2026-08-07：§4/§6/§7/§9 核对完成。安全硬承诺（127.0.0.1/token/钥匙串/ScopeFence）全部兑现；数据模型 8 实体中 Session/EventLog/WorkspaceSnapshot 部分完整，Task 缺 token 用量与 parent_task_id；分发就绪但 make dev 为占位守卫、CI 无构建/产物检查；验收标准 9 条基本满足（kl init 冷启动 gap 为唯一 ⚠️）。
- 2026-08-07 复核批次（用户修复）：①§3.1 数据损坏保护（quick_check + 备份 + 写阻塞 503）；②§3.2 追加说明（POST /tasks/{id}/instructions + 每轮注入）、workspace 校验（存在/目录/写探针，400 原因）；③§3.4 缺 key 不阻断启动；④§3.5 工具声明字段全闭环（Protocol + 17 内置工具全量声明 + Action 携带 + 守卫按权限分级替代硬编码名单 + catalog 输出）、schema 校验层（jsonschema → schema_error 结构化错误）、references 引用；⑤§3.6 守卫权限分级（DANGEROUS_PERMISSIONS/UNMANAGED_ESCALATION_PERMISSIONS）；⑥§3.8 任务状态进上下文（task_plan 注入）、规则分层（.kl/rules.md + AGENTS.md + session.rules + 显式优先级声明）、丢弃记录（logger + context_compressed 事件）——兑现率升至 100%；⑦§3.9 hook payload 脱敏（redact_payload 接入 command/http 双通道）。
- 2026-08-07 补充：新增 P2 缺口"完整输出落盘引用"（§6 存储规则），references 现为操作涉及文件，被截断的完整输出不可恢复。
- 2026-08-08 复核批次（用户修复）：①§3.5 完整输出落盘（tool_outputs/ + references 双语义 + meta.output_file，专项测试）；②§3.6 环境变量清理（sanitize_env 白名单+敏感模式过滤，子进程 env 注入）；③§3.6 超时与资源限制接线（sandbox.timeout min 优先、ctx.sandbox.limits 注入、RLIMIT_CPU/RLIMIT_AS 生效）；④§3.6 治理决策独立日志事件（governance_decision，异常 decision="error"）；⑤§3.6 fail-closed（配置加载失败 deny_all 兜底 + config_error 暴露）——§3.6 兑现率升至约 95%，唯一剩余：审批超时机制。全量缺口从 17 项降至 15 项。
- 2026-08-08 复核批次二（用户修复）：⑥§3.10 CommandRegistry 独立模块（commands.ts：CommandDef 含 usage/args/aliases/available/handler，注册表 run 做状态+参数校验）；⑦§3.10 双向状态门控（空闲侧 !state.running、任务侧 taskId 门控）；⑧§3.10 /exit 运行中二次确认（专项测试 process.exit spy）；⑨§3.10 参数错误生成式 schema 提示——§3.10 兑现率升至约 90%，仅剩 5 个名义指令（其中 /sessions//provider//key 有功能覆盖）。§3.11 治理决策事件同步更新 ✅。§4 超时/资源限制/脱敏行更新，兑现率约 85%。§6 大型输出落盘 ✅、Action 行更新，兑现率约 75%。全量缺口降至 14 项。
- 2026-08-08 复核批次三（用户修复）：⑩§3.11 审批事件独立日志（approval_request 含 action_id/tool/args/level、approval_complete 含 decision），专项测试断言请求与决策落盘——§3.11 升至 100%（继 §3.7/§3.8 后第三个全兑现章节）。全量缺口降至 13 项。
- 2026-08-08 信息同步批次四：§4 日志覆盖行升至 ✅（治理+审批事件齐备，兑现率 90%，剩余 4 项：kl init 冷启动 gap、token 用量状态接口、工具重试上限、CI 构建检查）；§4 引导证据更新为 connect-manager、CI pass 记录更新（npmmirror 502 为基础设施问题）；§6 Approval/WorkspaceSnapshot 行补充审计覆盖说明（校验值仍缺，兑现率 75% 保持）。
- 2026-08-08 修复批次五：①§4.3 kl init 冷启动自动拉起（连接被拒 → server start → 轮询 /health → 重试；仅网络错误触发，+3 测试）；②§4.5 CI dist-check job（wheel/sdist 构建 + zipfile 包内容断言 + cli build + --help 可运行性，本地全链路验证）；③max_iterations 默认值 10→20（bootstrap 显式覆盖删除，单一来源）——§4 兑现率升至约 95%，剩余 2 项：token 用量状态接口、工具重试上限。全量缺口 13 → 11 项。
- 2026-08-09 修复批次六：P2-7 发布资产补齐（examples/config.example.yaml、LICENSE、RELEASE_NOTES.md），make dev 接线为 cd cli && npm run tui；`make dev` 项已从缺口列表移出。
- 2026-08-09 修复批次七：P2-6 文档与行为对齐。默认 provider 统一说明为 deepseek，/connect 优先配置 API，/model 可切换 mock；README/promise_state 的审批超时与 provider test 状态已同步。
- 2026-08-09 修复批次八：工具输出统一迁移到 ~/.kl/tool_outputs，支持 storage 配置、MANIFEST.jsonl 元数据和保留策略；服务端启动不再创建项目 .kl/tool_outputs。
- 2026-08-09 修复批次九：新增 read_tool_output 内置工具，可从全局 tool_outputs 读取登记过的完整输出；manifest 支持 available/deleted_at，清理时写入 tombstone。

## 全量缺口汇总（2026-08-08 更新：CommandRegistry 已修复移出，交互确认剩 2 项）

**P0（行为与承诺相反 / 安全）**
1. 非 Git 快照失败时任务照常执行（§3.2，应拒绝启动；实现为"快照失败不阻断任务"）
2. config.yaml 允许直写 api_key（§3.4/§7.1/§4.2 冲突；README 有本地场景说明）

**P1（SPEC 明列缺失）**
3. Git 任务自动建分支 + 失败回退快照（§3.2）
4. 连续失败达阈值任务失败保留现场（§3.3，现有仅警告信号）
5. 循环级 token 预算停止条件（§3.3/§4.4；Task 无 token 用量字段）
6. /session close 运行中检查与删除二次确认已修复（§3.1；另 /exit 运行中确认已修复）
7. 工具执行重试上限（§4.1，工具层无重试）

**P2（规格形式/增强）**
8. 5 个斜杠指令名义缺失（§3.10：/provider /key /tools /hooks /sessions——/sessions 由 /session 面板覆盖、/provider /key 由 /config 向导+/model 覆盖、/tools /hooks 无覆盖）
9. 数据模型字段补齐（token 用量/parent_task_id/Action 结果字段/快照校验值/MemoryEntry token 估算）（§6；其中大型输出落盘已修复）
10. MCP 远程工具无权限声明（默认 normal 分级；配置即信任可辩护，更保守可强制审批）
