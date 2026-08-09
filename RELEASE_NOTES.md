# Release Notes

## 0.1.0 (2026-08-09)

> 当前为开发快照，尚未发布到 PyPI / npm。此文件用于正式发布前核对变更、已知问题和升级注意事项。

### Added

- 本地 daemon 生命周期：`kl server start|stop|status`、自动拉起、空闲自动回收、手动 daemon 接管。
- 全局运行时目录：配置、数据库、记忆、审计日志、daemon token 统一位于 `~/.kl/`。
- 全局用户规则：`~/.kl/user-rules.md`，优先于项目规则。
- 全局 skills / tools：`~/.kl/skills/`、`~/.kl/tools/`。
- TUI：会话管理、skill 列表、MCP 管理、模型切换、API 连接配置、命令菜单、滚轮滚动、审批倒计时。
- AgentLoop：原生 OpenAI tool calling、工具反馈闭环、上下文压缩、任务计划注入、续接上下文。
- 18 个内置工具：文件、搜索、patch、shell、git、测试、lint、typecheck、task_manage、read_tool_output。
- 扩展能力：MCP 远程工具发现、用户 Python 工具插件、command/http hooks。
- 发布资产：`examples/config.example.yaml`、`LICENSE`、`RELEASE_NOTES.md`。

### Changed

- 配置和数据不再从项目目录 `.kl/` 读取；旧项目配置需要迁移到 `~/.kl/config.yaml`。
- session 规则不再注入上下文；规则优先级调整为“用户指令沉淀 > 全局用户规则 > 项目规则 > 默认行为”。
- 审批超时默认 300 秒，超时自动拒绝动作。
- `make dev` 已接线：构建 CLI 并启动 TUI，服务端未运行时由 TUI 自动拉起 daemon。

### Fixed

- `kl run` 创建 session 后再提交 task，避免缺失默认 session 导致 500。
- 自动拉起 daemon 不再误用旧 worktree 的 `kl_server`。
- daemon Ctrl+C 优雅关闭增加超时，避免 WebSocket 挂住导致进程无法退出。
- 审批事件双通道覆盖问题：TUI 不再因嵌套 payload 显示 `undefined`。
- hook payload 自动脱敏，command/http 双通道生效。
- MCP tool 返回 `isError=true` 时保留真实错误文本，不再折叠成固定错误标记。

### Known Issues

- `run_command` 当前不是 OS 级文件系统沙箱，默认 allow 为空时仍可能执行任意本机命令；正式发布前应改为显式 allowlist 或接入进程隔离。
- 凭据保护存在本地文件读取风险：keyring 不可用时主密码与密文同存 `~/.kl`，且配置允许明文 `api_key`；API Key 建议通过 `/connect` 保存。
- Git 任务不会自动创建任务分支；非 Git 快照失败时任务仍会继续执行。
- daemon 重启后非终态任务不会自动恢复或标记失败。
- 运行时上下文压缩失败时可能丢弃旧历史。
- 命令类工具的输出在执行层先截断到 8000 字符，“完整输出落盘”无法恢复开头内容。
- 审计日志对 `command` 字段整体脱敏，重新打开历史会话时工具参数显示为 `[REDACTED]`。
- `docs/promise_state.md` 仍在同步中，部分历史核对记录早于 server-redesign 实施。

### Upgrade Notes

1. 安装要求：Python `>=3.11`、Node.js `>=22`。
2. 首次运行前复制 `examples/config.example.yaml` 到 `~/.kl/config.yaml`，并按需配置 provider。
3. 真实 API key 优先通过 `kl connect` 或 `kl config key set` 写入，不要直接写进配置文件。
4. 旧项目的 `.kl/config.yaml`、`kl.db`、`memory.db`、`audit.jsonl` 不再由当前 daemon 使用；迁移到 `~/.kl/` 后再启动。
5. 发布 tag 建议使用 `v0.1.0`，发布前运行 server 测试、CLI 测试、TypeScript 检查和版本一致性检查。
