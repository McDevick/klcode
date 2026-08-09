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

### P1-1 运行中的 session 可被 close/delete

- 位置：`server/kl_server/api/routes.py:623-658`、`server/kl_server/core/task_manager.py:88-105`
- 风险：`close_session` 和 `delete_session` 不检查该 session 是否正在运行任务。删除会先删除 tasks 行，后台 `_execute_task` 后续 `update(task)` 会找不到行，可能以未处理异常结束或留下状态不一致。
- 后果：用户误删会话时，已产生的代码变更不会回滚，后台任务可能继续执行但没有可靠结束事件。
- 建议：close/delete 前检查 active task，要求先 abort；TUI 删除会话前增加二次确认。

### P1-2 daemon 重启后任务状态无恢复

- 位置：`server/kl_server/api/routes.py:54`、`server/kl_server/api/routes.py:734`、`server/kl_server/api/app.py:38`
- 风险：`_running_tasks` 只是进程内 dict；服务崩溃或重启时，SQLite 中 `running`、`awaiting_approval`、`paused` 状态不会被清理或标记失败。
- 后果：任务实际已死但状态永久卡住，TUI 会显示运行中/等待审批；`/abort` 可以清理，但用户必须先发现。
- 建议：启动时把非终态任务标记为 failed/canceled，或至少提供 `/status` 中的 stale 状态和恢复入口。

### P1-3 运行时上下文压缩失败会直接丢历史

- 位置：`server/kl_server/core/context.py:373-399`、`server/kl_server/core/agent_loop.py:609-642`
- 风险：`compact_messages` 在 LLM 摘要失败时返回空 `summary`，但仍返回缩短后的 history；`agent_loop` 判断 `len(recent_history) < len(history)` 后直接替换 history。
- 后果：provider 临时不可用时，旧对话、决策和失败原因被静默丢弃，任务继续时“失忆”，且无法自动恢复。
- 建议：摘要失败时不替换 history，而是保留最近可容纳的消息并注入明确的压缩失败信号；或把旧消息先落盘，下次再恢复。

### P1-4 完整输出落盘对命令类工具不完整

- 位置：`server/kl_server/tools/builtin/shell.py:65-66`、`server/kl_server/core/tool_executor.py:50-75`
- 风险：`run_command`/`run_tests`/`run_lint` 在执行层就只保留 stdout/stderr 末尾 8000 字符；`ToolExecutor` 的“完整输出落盘”只针对返回结果超过 20k 的情况。
- 后果：长测试输出开头的关键错误、编译错误或日志会被永久丢失，`[文件引用]` 也不能恢复它们。
- 建议：shell 工具本身不截断原始输出，把截断和落盘统一交给 `ToolExecutor`；或直接在 shell 层落盘完整 stdout/stderr 并返回引用。

### P1-5 历史回放丢失工具参数和长输出

- 位置：`server/kl_server/core/event_logger.py:16`、`server/kl_server/api/routes.py:237-244`、`server/kl_server/core/agent_loop.py:826-832`
- 风险：审计日志把 `command` 整体替换为 `[REDACTED]`，并且 `tool_result.output` 只写 500 字符。TUI 实时事件走 WS 可以看到原始参数，但重新打开 session history 时，工具行会变成 `run_command("[REDACTED]")`，长结果也被截断。
- 后果：历史会话的“聊天流”不完整，用户无法知道之前实际执行了什么命令。
- 建议：审计时只脱敏真实密钥/参数值，保留命令结构；history 中输出只放摘要，同时附上 `tool_outputs` 文件引用并可点击打开。

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

### P2-1 session/task ID 生成存在并发竞争

- 位置：`server/kl_server/api/routes.py:415-437`、`server/kl_server/api/routes.py:660-695`
- 风险：`next_session_id`/`next_task_id` 采用“先 list 再 +1”的 read-modify-write；两个并发请求在 await 处交错时可能算出同一个 ID，主键冲突返回 500。
- 建议：用数据库自增/唯一 ID，或在同一个事务内通过 `MAX(id)` 原子分配并捕获冲突重试。

### P2-2 WS 重连不补发错过的任务事件

- 位置：`cli/src/api/events.ts:45-115`
- 风险：任务事件 WS 会指数退避重连，但只续传之后的新事件；断线期间发生的 `tool_result`、`task_end`、审批结果不会补发。
- 后果：TUI 可能停在“运行中”，用户需要刷新/重开会话才能恢复视图。
- 建议：重连后拉取任务状态和历史，补齐缺失事件，或为每个任务提供从序号/游标补发的 WS 协议。

### P2-3 删除 session 不清理 memory 普通记录

- 位置：`server/kl_server/api/routes.py:648-654`、`server/kl_server/memory/store.py:56-60`
- 风险：删除 session 只清理 `state` 中的 task_plan/continuation/instructions，`tool_result`、`feedback`、`context_summary` 等 memory 行仍留在全局 `memory.db`。
- 后果：隐私数据和磁盘占用不会随会话删除释放；若后续 session 使用相同 tags 或关键词，可能被检索到旧内容。
- 建议：删除 session 时级联清理对应 memory 行，或至少提供清理 API。

### P2-4 MCP server 添加/刷新失败不够可见

- 位置：`server/kl_server/api/routes.py:910-935`、`server/kl_server/extensions.py:96-104`
- 风险：MCP server 不可达或 schema 非法时，`register_mcp_tools` 只写 warning 并继续；`add_mcp` 仍然持久化配置并返回“已添加”结果，TUI 可能看到 0 tools 但不知道原因。
- 建议：`add/refresh` 返回明确 `error`/`tools` 状态，或至少让 TUI 展示发现失败原因。

### P2-5 数据文件无轮转，历史读取全量扫日志 ⚠️ 部分已处理（2026-08-09）

- 位置：`server/kl_server/api/routes.py:291-307`、`server/kl_server/core/event_logger.py:40-52`
- 风险：`audit.jsonl`、`memory.db` 仍只增长；`tool_outputs/` 已支持保留天数/容量上限，但每次 `/history`、`/context` 仍读取整个 audit 文件再过滤。
- 后果：长期运行后磁盘占用和接口延迟都会上升。
- 建议：日志轮转、memory 清理策略、按 session/task 索引查询历史；tool_outputs 保留策略已实现。

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
2. 再处理 P1-1/P1-2：session/task 生命周期和 daemon 重启恢复。
3. 然后处理 P1-3/P1-4/P1-5：压缩失败保底、完整输出落盘、历史回放。
4. 继续处理 P2-1..P2-5 等剩余风险；P2-6/P2-7 已完成。
