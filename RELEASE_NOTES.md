# Release Notes

## 0.1.0 (2026-08-10)

> 已发布：npm `kl-code-cli@0.1.0`、PyPI `kl-server@0.1.0`、GitHub Release `v0.1.0`。


### 安装

普通用户直接安装 CLI，首次启动会自动准备 server：

```powershell
npm install -g kl-code-cli
kl init
kl tui
```

如果希望手动安装 server，可以额外执行：

```powershell
python -m pip install kl-server
```

### Release Assets

GitHub Release `v0.1.0` 提供以下资产：

- `checksums.sha256`
- `kl-code-cli-0.1.0.tgz`
- `kl_server-0.1.0-py3-none-any.whl`
- `kl_server-0.1.0.tar.gz`

GitHub 自动生成的 `Source code (zip)` / `Source code (tar.gz)` 是源码归档，主要用于审计或从源码运行。

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
- session/task ID 改为数据库原子序列，避免并发创建冲突。
- 运行中的 session 禁止 close/delete，TUI 删除会话增加二次确认。
- daemon 重启后 stale 任务自动标记 failed，不再永久卡在非终态。
- 上下文压缩失败时执行确定性裁剪并落盘快照，不再静默丢历史。
- 命令类工具不再在工具层截断 stdout/stderr，完整输出统一落盘。
- 历史脱敏保留命令结构，只脱敏真实密钥；历史回放按 task 分片，不再全量扫描 audit。
- 删除 session 时级联清理 memory、tool_outputs 与历史分片。
- WS 重连会补发最近任务事件，客户端按 event_id 去重。
- MCP 发现失败会在 /mcp 与 TUI 中展示 status/error。

### Known Issues

- `run_command` 当前不是 OS 级文件系统沙箱，默认 allow 为空时仍可能执行任意本机命令；正式发布前应改为显式 allowlist 或接入进程隔离。
- 凭据保护存在本地文件读取风险：keyring 不可用时主密码与密文同存 `~/.kl`，且配置允许明文 `api_key`；API Key 建议通过 `/connect` 保存。
- Git 任务不会自动创建任务分支；非 Git 快照失败时任务仍会继续执行（P1-8，当前版本不处理）。
- 上下文 token 预算仍使用估算，没有真实 tokenizer/usage 和循环级硬停止（P1-6，当前版本不处理）。
- command/http hook 仍同步执行，慢 hook 可能阻塞事件循环（P1-7，当前版本不处理）。

### Upgrade Notes

1. 安装要求：Python `>=3.11`、Node.js `>=22`。
2. 首次运行前复制 `examples/config.example.yaml` 到 `~/.kl/config.yaml`，并按需配置 provider。
3. 真实 API key 优先通过 `kl connect` 或 `kl config key set` 写入，不要直接写进配置文件。
4. 旧项目的 `.kl/config.yaml`、`kl.db`、`memory.db`、`audit.jsonl` 不再由当前 daemon 使用；迁移到 `~/.kl/` 后再启动。
5. 发布 tag 建议使用 `v0.1.0`，发布前运行 server 测试、CLI 测试、TypeScript 检查和版本一致性检查。
6. CLI 唯一官方安装方式为 `npm install -g kl-code-cli`；`npx kl-code-cli` 只是临时执行，不会注册全局 `kl`。
7. `pip install kl-server` 只注册服务端命令 `kl-server`，不会注册 `kl`。
8. 如果找不到 `kl`，检查 npm 全局 bin 是否在 PATH：
   ```bash
   npm config get prefix
   npm bin -g
   ```
