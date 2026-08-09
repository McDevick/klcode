# KL Code 发布前测试与检查清单

> 状态：草案（2026-08-09）
> 目标：正式发布前验证构建产物、全新环境安装、真实功能、数据持久化、安全与发布资产，避免把开发环境状态当成可发布状态。

## 1. 当前基线

每次发布前应以目标 commit 的实际测试结果为准。当前开发基线：

| 检查 | 命令 | 结果参考 |
|---|---|---|
| Server 测试 | `python -m pytest server/tests -q` | `538 passed, 1 skipped` |
| CLI 测试 | `cd cli && npm test` | `124 passed` |
| TypeScript | `cd cli && npx tsc --noEmit` | 通过 |
| 版本一致性 | `cd cli && npm run check:server-version` | `0.1.0` |

## 2. 构建与包内容

```bash
python -m build server
cd cli
npm run build
npm pack --dry-run
```

检查点：

- [ ] `server/dist/kl_server-<version>-py3-none-any.whl` 存在。
- [ ] `server/dist/kl_server-<version>.tar.gz` 存在。
- [ ] CLI `npm pack --dry-run` 只包含 `dist` 和 package metadata。
- [ ] `server/pyproject.toml` 与 `cli/src/server-version.ts` 版本一致。
- [ ] 包内没有 `.kl`、`kl.db`、`memory.db`、`audit.jsonl`、`daemon.token`、日志、密钥、venv、node_modules。

## 3. 全新环境安装冒烟

### 3.1 Python venv

```bash
python -m venv /tmp/kl-release-venv
/tmp/kl-release-venv/Scripts/python -m pip install server/dist/kl_server-0.1.0-py3-none-any.whl
/tmp/kl-release-venv/Scripts/kl-server --help
/tmp/kl-release-venv/Scripts/python -c "import uvicorn, fastapi, websockets, kl_server"
```

### 3.2 Node CLI

```bash
cd cli
npm pack
npm install -g kl-code-cli-0.1.0.tgz
kl --help
```

检查 `kl` 是否真的在 PATH 中：

```powershell
Get-Command kl
npm bin -g
```

如果 `kl` 找不到，将 npm 全局 bin 加入 PATH 后重新验证；`npx @kl-code/cli` 只能临时使用，不视为“kl 已注册”。

Server 独立安装只注册 `kl-server`：

```bash
/tmp/kl-release-venv/Scripts/kl-server --help
```

### 3.3 冷启动冒烟

```bash
kl init
kl server status
kl run "hello"
kl tui
```

检查点：

- [ ] 全新环境能 `kl init`。
- [ ] 未运行 daemon 时能自动拉起。
- [ ] `kl run` 能创建 session/task。
- [ ] `kl tui` 能启动并创建会话。
- [ ] 首次启动不创建项目目录 `.kl/skills` / `.kl/tools`。
- [ ] `~/.kl/tool_outputs` 与 `~/.kl/history` 正常生成。

## 4. 真实功能回归

### 4.1 Provider

- [ ] 默认 provider 为 `deepseek`。
- [ ] 通过 `/connect` 配置 deepseek API Key。
- [ ] 提交真实任务能获得模型回复，不出现 `provider http error: 400`。
- [ ] 通过 `/model` 切换到 `mock`，无 key 也能运行。
- [ ] provider 连接测试返回真实调用结果，而不是仅检查 provider 存在。

### 4.2 AgentLoop 与工具

- [ ] 文件读写、搜索、patch、git、测试命令基本流程可用。
- [ ] 长命令输出完整落盘到 `~/.kl/tool_outputs/`。
- [ ] `read_tool_output` 能读取已登记完整输出。
- [ ] 输出文件删除后 `read_tool_output` 返回 `output file not found`。
- [ ] 上下文压缩成功时历史缩短并生成摘要。
- [ ] 压缩失败时执行确定性裁剪，并注入快照引用，不撑爆上下文。
- [ ] 任务在 `max_iterations` 后明确失败，不会误报成功。

### 4.3 审批与 HITL

- [ ] 危险命令弹出审批面板。
- [ ] approve / reject / abort 均能正确闭环。
- [ ] 审批超时自动拒绝，TUI 显示超时提示。
- [ ] 审批事件写入审计日志。

### 4.4 Session / Task 生命周期

- [ ] 创建、重命名、切换、历史回放正常。
- [ ] 运行中 session 无法 close/delete。
- [ ] abort 后可以关闭/删除 session。
- [ ] 删除 session 级联清理 memory、tool_outputs、history。
- [ ] daemon 重启后 stale 任务标记为 failed，不会永久卡住。

### 4.5 WS 与 MCP

- [ ] server 环境包含 `websockets`，WS 能正常连接，不再出现 `No supported WebSocket library detected`。
- [ ] TUI WS 重连后能补发最近事件。
- [ ] 相同 `event_id` 不会重复处理。
- [ ] MCP 不可达时 `/mcp` 面板显示 `status: error` 和具体原因。
- [ ] MCP 可用时工具能正常发现并调用。

## 5. 安全与数据检查

- [ ] 仓库无真实 API Key：
  ```bash
  rg -n "sk-|api_key|api-key|token|secret|password" --glob '!node_modules/**' --glob '!tmp/**'
  ```
- [ ] CLI 依赖审计：
  ```bash
  cd cli && npm audit --omit=dev
  ```
- [ ] Python 依赖审计：
  ```bash
  pip install pip-audit
  pip-audit
  ```
- [ ] `~/.kl` 不进入发布包。
- [ ] 发布前明确记录当前不处理的风险：
  - P0-1 `run_command` 不是 OS 级沙箱。
  - P0-2 本地凭据保护不足。
  - P1-6 token 预算。
  - P1-7 hook 同步阻塞。
  - P1-8 快照/Git 边界。

## 6. 发布资产

- [ ] `LICENSE` 存在。
- [ ] `RELEASE_NOTES.md` 已写明新增、修复、已知问题、升级说明。
- [ ] `examples/config.example.yaml` 能加载，默认 provider 为 `deepseek`。
- [ ] `release/checksums.sha256` 已生成。
- [ ] 可选：SBOM 已生成。
- [ ] GitHub Release Notes 与 `RELEASE_NOTES.md` 一致。

## 7. 账号与 CI

- [ ] PyPI `kl-server` 包名已注册。
- [ ] npm `@kl-code/cli` 包名已注册。
- [ ] `cli/package.json` 已移除 `"private": true`。
- [ ] 发布 token 已配置为环境变量或本地凭据，不进入仓库。
- [ ] tag 使用 `v<version>`。
- [ ] 建议增加 `.github/workflows/release.yml`，tag 触发自动构建、上传产物、创建 GitHub Release。

## 8. 执行结论

每次发布前按本清单逐项勾选，并把执行结果补充到 `docs/release-test.md`：

- 测试日期
- 测试 commit
- 通过/失败项
- 阻塞问题
- 发布结论