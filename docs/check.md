# KL Code 风险检查

> 日期：2026-08-09
> 分支：`dev`
> 方法：代码审读 + 静态扫描 + 全量测试
> 结论：当前测试全绿，但项目仍存在安全边界、任务恢复、上下文压缩、历史完整性和文档同步方面的实质风险；其中 `run_command` 的权限模型是当前最需要优先处理的问题。

## 1. 当前验证基线

| 检查 | 结果 |
|---|---|
| Server 测试 | `516 passed, 1 skipped` |
| CLI 测试 | `122 passed` |
| CLI TypeScript 检查 | `npx tsc --noEmit` 通过 |
| 版本一致性 | `npm run check:server-version` 通过，`0.1.0` |

## 2. P0：安全边界

### P0-1 `run_command` 不是真正的文件系统沙箱（当前版本不处理）

- 位置：`server/kl_server/tools/builtin/shell.py:47-66`、`server/kl_server/core/sandbox.py:122-148`
- 风险：命令工具以 `shell=True` 执行模型提供的字符串；SandboxPolicy 只做二进制名、包装器和未加引号元字符的粗筛，没有限制工作目录或可访问文件系统。默认 allow 为空时，除 `rm/docker` 等少数 deny 外，`python -c`、`cmd` 别名、直接调用系统工具都可用。
- 后果：一个被仓库内容诱导的模型可以读取/写入 workspace 外文件，读取 `~/.kl` 下的配置、凭证或记忆库，执行 `git push`，甚至调用外部网络。`ScopeFence` 只拦截带 `path` 参数的内置文件工具，不限制 `run_command` 的 shell 文本。
- 建议：至少在 P0 阶段把默认命令权限改为显式 allowlist，并说明 `run_command` 不属于 OS 级安全边界；后续应接入真实进程隔离（容器、Windows Job Object、WSL、沙箱用户等）。
- 当前版本：不处理；已作为“本地完整权限模式”写入 README 已知限制，正式发布/共享使用前应重新评估。

### P0-2 凭据保护仍允许“同目录可解密”和明文配置（当前版本不处理）

- 位置：`server/kl_server/config/config.py:33`、`server/kl_server/bootstrap.py:75-83`、`server/kl_server/config/backends.py:38-83`
- 风险：`config.yaml` 仍允许直接写 `api_key`；keyring 不可用时，加密文件的主密码以纯文本保存在同一个 `~/.kl/credentials.master`。攻击者如果已经能读取 `~/.kl`，通常也能同时读到主密码和密文。
- 后果：配置文件被同步、备份或误提交时，明文 key 会直接泄漏；本地文件被读取时，加密回退方案也无法提供有效保护。
- 建议：正式发布时禁止 `api_key` 直写，或在文档中明确这是“本地临时场景”；AES 回退方案应改为提示用户输入主密码，而不是把主密码与密文放同一目录。
- 当前版本：不处理；已写入 README 已知限制，API Key 仍推荐通过 `/connect` 保存。

## 3. P1：稳定性和数据完整性

### P1-1 运行中的 session 可被 close/delete ✅ 已处理（2026-08-09）

- 位置：`server/kl_server/api/routes.py`、`cli/src/tui/components/session-manager.tsx`
- 修复：session 存在 `running`、`awaiting_approval`、`paused` 任务时，`close`/`delete` 返回 409；用户需要先 abort 后再操作。TUI 删除会话增加二次确认。
- 验证：close/delete 拦截测试、abort 后删除成功测试、TUI 二次确认测试通过。

### P1-2 daemon 重启后任务状态无恢复 ✅ 已处理（2026-08-09）

- 位置：`server/kl_server/core/task_manager.py`、`server/kl_server/api/app.py`
- 修复：daemon 启动时把 SQLite 中的 `running`、`awaiting_approval`、`paused` 任务统一标记为 `failed`，summary 为 `daemon restarted before task completed`；`pending` 和终态任务保持不动。
- 验证：TaskManager recover 单测 + runtime_factory 启动生命周期测试通过。

### P1-3 运行时上下文压缩失败会直接丢历史 ✅ 已处理（2026-08-09）

- 位置：`server/kl_server/core/context.py`、`server/kl_server/core/agent_loop.py`
- 修复：压缩摘要失败或无 summarizer 时抛出 `ContextCompressionError`；AgentLoop 捕获后先执行确定性裁剪，将旧上下文快照写入全局 tool_outputs，再保留最近消息并向模型注入 `read_tool_output` 引用。如果快照落盘失败才保留完整历史，并带 2 轮压缩冷却，避免反复失败导致上下文超限。
- 验证：`compact_messages` 失败抛异常、确定性 fallback、AgentLoop 快照引用、冷却逻辑测试通过。

### P1-4 完整输出落盘对命令类工具不完整 ✅ 已处理（2026-08-09）

- 位置：`server/kl_server/tools/builtin/shell.py`、`server/kl_server/core/tool_executor.py`
- 修复：`run_command` 不再在执行层截断 stdout/stderr，完整输出返回给 `ToolExecutor`；由 `ToolExecutor` 统一截断、摘要并落盘到全局 tool_outputs。
- 验证：run_command 大输出完整落盘测试 + 输出摘要测试通过。

### P1-5 历史回放丢失工具参数和长输出 ✅ 已处理（2026-08-09）

- 位置：`server/kl_server/core/event_logger.py`、`server/kl_server/core/agent_loop.py`、`server/kl_server/api/routes.py`
- 修复：
  - 审计/历史脱敏改为只脱敏真实密钥值，保留命令结构，例如 `pytest --token [REDACTED]`。
  - `tool_result` 历史输出上限从 500 提升到 4000，并保留 `[文件引用]` 与全局 tool_outputs 引用。
  - 历史回放继续通过 `read_tool_output` 恢复完整输出。
- 验证：EventLogger 命令结构保留测试 + 历史回放工具参数脱敏测试通过。

### P1-6 上下文预算估算不准确，且无循环级 token 硬限制（当前版本不处理）

- 位置：`server/kl_server/core/context.py:239-241`、`server/kl_server/core/context.py:310-316`、`server/kl_server/providers/openai_compatible.py:46`
- 风险：token 估算用 `len(text) / 4`，不是模型真实 tokenizer；`/context` 和压缩阈值都会系统性偏差。工具 schema、当前模型输出预算也未完整计入；AgentLoop 调用 provider 时没有设置 `max_tokens`，也没有读取 usage 做停止。
- 后果：实际请求可能超过模型上限，或压缩过早/过晚；长任务只能靠 `max_iterations=20` 兜底。
- 建议：接入模型返回的 usage/tokenizer 或按 provider 配置合理保守系数，并把循环级 token 预算作为正式停止条件。
- 当前版本：不处理；已写入 README 已知限制。

### P1-7 钩子同步阻塞事件循环（当前版本不处理）

- 位置：`server/kl_server/hooks/manager.py:121-142`
- 风险：`HookManager.run` 是同步方法，`subprocess.run` 和 `httpx.post` 都在 async 循环内直接执行，最长可阻塞 30 秒。
- 后果：配置一个慢 hook 后，其他任务的 LLM 调用、WS 事件和 API 请求都会同时卡住。
- 建议：把 hook 执行迁移到 `asyncio.to_thread` 或改为真正异步 client，并给每个 hook 单独超时。
- 当前版本：不处理；已写入 README 已知限制。

### P1-8 快照失败仍继续任务，Git 模式无自动分支（当前版本不处理）

- 位置：`server/kl_server/api/routes.py:1076-1084`、`README.md:284`
- 风险：unmanaged 模式快照失败只把 `snapshot_path` 置空，任务照常执行；managed/git 模式不会自动建任务分支，`run_command` 还允许普通 `git push`。
- 后果：任务失败或误改后缺少可回滚边界，可能污染当前分支或远程仓库。
- 建议：快照失败默认拒绝启动；Git 模式自动建分支，并禁止任务直接 push 到当前分支，除非用户显式审批。
- 当前版本：不处理；已写入 README 已知限制。

## 4. P2：并发、体验和文档风险

### P2-1 session/task ID 生成存在并发竞争 ✅ 已处理（2026-08-09）

- 位置：`server/kl_server/storage/database.py`、`server/kl_server/core/session_manager.py`、`server/kl_server/core/task_manager.py`
- 修复：新增 `id_sequences` 表，`Database.next_sequence()` 使用 `INSERT ... ON CONFLICT ... RETURNING` 原子分配；Session/Task Manager 通过 `next_id()` 生成 `sN`/`tN`。
- 兼容：旧库启动时按现有 `sN`/`tN` 的最大序号初始化 sequence，避免与历史 ID 冲突。
- 验证：并发分配唯一性测试 + 旧库 seed 测试通过。

### P2-2 WS 重连不补发错过的任务事件 ✅ 已处理（2026-08-09）

- 位置：`server/kl_server/api/task_events.py`、`server/kl_server/api/ws.py`、`cli/src/api/events.ts`
- 修复：TaskEventBus 为每个任务保留最近 500 条事件并生成 `event_id`；新 WebSocket 连接建立后先 `replay` 补发历史事件。
- 客户端：重连连接复用同一 `event_id` 去重集合，补发事件不会重复处理。
- 验证：服务端 replay 测试 + WS 重连补发测试 + CLI event_id 去重测试通过。

### P2-3 删除 session 不清理 memory 普通记录 ✅ 已处理（2026-08-09）

- 位置：`server/kl_server/api/routes.py`、`server/kl_server/memory/store.py`、`server/kl_server/core/tool_executor.py`
- 修复：删除 session 时级联清理：
  - `state` 中的 task_plan/continuation/instructions。
  - `memory` 表中该 session 的 feedback/tool_result/context_summary 等记录。
  - `~/.kl/tool_outputs/<session_id>/` 目录。
  - `MANIFEST.jsonl` 中该 session 的 output 记录。
- 验证：memory scope 清理、tool_outputs 目录与 manifest 清理、route 级联删除测试通过。

### P2-4 MCP server 添加/刷新失败不够可见 ✅ 已处理（2026-08-09）

- 位置：`server/kl_server/extensions.py`、`server/kl_server/mcp/adapter.py`、`server/kl_server/api/routes.py`、`cli/src/tui/components/mcp-manager.tsx`
- 修复：MCP 发现失败时记录 `last_errors`；`/mcp`、add/refresh 响应返回 `status` 与 `error`；TUI 在列表和刷新结果中展示失败原因。
- 验证：扩展层错误记录测试 + `/mcp` status/error 测试通过。

### P2-5 数据文件无轮转，历史读取全量扫日志 ✅ 已处理（2026-08-09）

- 位置：`server/kl_server/api/routes.py:291-307`、`server/kl_server/core/event_logger.py:40-52`
- 风险：每次 `/history`、`/context` 读取整个 audit 文件，会话切换会随日志增长越来越慢；memory 与 tool_outputs 缺少删除级联。
- 后果：长期运行后磁盘占用和接口延迟都会上升。
- 修复：历史事件按 task 分片写入 `~/.kl/history/<task_id>.jsonl`，历史回放只读目标 task 分片；旧 audit 仅作为缺失分片时的 fallback。删除 session 时级联清理 memory、tool_outputs、task 历史分片。audit.jsonl 继续作为审计日志保留。

### P2-6 文档与当前行为漂移 ✅ 已处理（2026-08-09）

- 状态：默认 provider、API 配置入口、审批超时和 provider test 的文档已对齐当前行为。
- 已明确：
  - 默认 provider 为 `deepseek`；首次使用优先通过 `/connect` 配置 API Key。
  - 可以使用 `/model` 切换为 `mock` 进行无 key 试跑。
  - 示例配置 `examples/config.example.yaml` 默认也改为 `deepseek`。
  - README/release-package/promise_state 已同步审批超时（默认 300s）和 provider test（真实 LLM 调用）状态。
- 剩余：无。

### P2-7 发布资产仍缺关键文件 ✅ 已处理（2026-08-09）

- 状态：已补齐基础发布资产，`make dev` 已接线。
- 已新增：
  - `examples/config.example.yaml`：deepseek 默认 provider、/connect API 配置、/model 切换 mock、sandbox、guardrail、注释 MCP 示例。
  - `LICENSE`：MIT。
  - `RELEASE_NOTES.md`：0.1.0 变更、已知问题、升级说明。
- 已接线：`make dev` -> `cd cli && npm run tui`，服务端未启动时由 TUI 自动拉起 daemon。
- 剩余：正式发布前的 wheel/npm 构建、上传、checksums/SBOM 等仍需按 `docs/release-package.md` 执行。

## 5. 建议处理顺序

1. P0-1/P0-2 当前版本不处理，已作为已知限制记录；正式发布或多人共享前再评估默认命令权限和凭据保护。
2. P1-1..P1-5 已完成。
3. P1-6/P1-7/P1-8 当前版本不处理，已写入 README 已知限制。
4. P2 系列风险已全部处理；后续如需审计日志轮转可另开专项。
