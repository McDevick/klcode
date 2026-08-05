# KL Code

> 原名：Simple Coding Agent

## 项目简介

**KL Code** 是一个 Coding Agent（编码智能体）项目。

本仓库目录名仍沿用 `SimpleCodingAgent`，但项目正式名称定为 **KL Code**，后续文档、命名、标识统一使用该名称。

当前进度：Phase 1–5 核心框架已全部实现并通过测试 —— 后端（模型、Provider、AgentLoop、工具系统、治理守卫、沙箱、反馈闭环、上下文/记忆、存储、MCP/插件/skills/hooks、bootstrap 服务端组装）与 CLI（init/run/server/config 命令、打包分发）均可运行。CLI TUI 组件已实现但仍未接线启动，属 roadmap（见”已知限制”）。

## 环境要求

- Python >= 3.11
- Node.js >= 22，含 npm

## 安装

推荐在有 `make` 的环境执行：

```bash
make install
```

Windows 无 `make` 时，在仓库根目录依次执行等价命令：

```powershell
python -m pip install -e "server[dev]"
cd cli
npm install
cd ..
```

CI 依赖安装（CLI 使用 `npm ci`）：

```bash
make ci
```

## 运行

运行服务端与 CLI 测试：

```bash
make test
```

等价命令：

```powershell
python -m pytest server/tests -q
cd cli
npm test
```

### 启动服务端（daemon）

服务端 bootstrap（Task 5.6）已完成，可直接启动：

```powershell
# 使用项目 venv 启动（本仓库开发 venv 路径）：
E:\projects\SimpleCodingAgent\.superpowers\sdd\PLAN\venv\Scripts\python.exe -m uvicorn kl_server.main:app --host 127.0.0.1 --port 8700
# 或激活 venv 后：
& E:\projects\SimpleCodingAgent\.superpowers\sdd\PLAN\venv\Scripts\Activate.ps1
python -m uvicorn kl_server.main:app --host 127.0.0.1 --port 8700
# 或已安装 server[dev] 后使用 console 入口：
kl-server
```

首次启动会自动创建 `~/.kl/daemon.token`，并在当前目录（workspace）生成 `.kl/`（`config.yaml`、`kl.db`、`audit.jsonl`、`memory.db`）。缺少 `config.yaml` 也能启动，默认 provider 为 `mock`。

`make dev`（roadmap，尚未可用）：

```bash
make dev
```

`make dev` 当前是占位守卫：输出 `make dev is not available until server main and cli tui entrypoints exist` 并以退出码 1 结束（服务端与 TUI 入口均已就绪，该目标待接线为"同时启动服务端与 TUI"）。

### CLI

CLI 计划程序名为 `kl`（`cli/src/main.ts` 中 `program.name('kl')`）。已配置 `bin` 与 esbuild 构建（`npm run build` → `cli/dist/main.js`）。开发期可从 `cli/` 目录直接运行：

```powershell
cd cli
npx tsx src/main.ts --help
```

或构建后链接为全局命令：

```powershell
cd cli
npm run build   # 生成 dist/main.js
npm link        # 之后可用 kl <命令>
```

已接线的子命令：

- `kl server start|stop|status`：管理本地守护进程。`start` 自动探测可用的 python（`python`/`python3`/`py`，要求能导入 uvicorn/fastapi/kl_server），用探测到的 python 以 `-m uvicorn kl_server.main:app --host 127.0.0.1 --port 8700` 拉起服务，PID 写入 `~/.kl/daemon.pid`；无可用 python 时返回明确错误提示。
- `kl init`：查询初始化状态。需要守护进程已运行，否则连接被拒而失败；请先启动 daemon。
- `kl run <task>`：提交一次性任务。自动创建 session（workspace 为当前目录）后提交，任务在服务端后台执行。
- `kl config <area> <action> ...`：管理 provider 与 key（如 `kl config provider list`、`kl config key show <ref>`）。`kl config key set` 写入服务端凭据库（keyring/内存回退）；`kl config provider add` 注册 provider 并写回 `.kl/config.yaml`（重启后仍生效）。
- `kl tui`：启动交互式 TUI（见下文"启动 TUI"）。

### 启动 TUI（交互界面）

先启动服务端（见上），然后打开 TUI：

```powershell
# 最简单：仓库根目录一条命令（自动构建并启动，等价于 node cli/dist/main.js tui）
npm run tui

# 或从 cli/ 目录：
cd cli
npx tsx src/main.ts tui          # 开发模式（免构建）
node dist/main.js tui            # 已构建过时
```

TUI 启动后自动创建 session（workspace 为当前目录）并连接服务端，支持：

- 输入任务回车 → 创建任务并在服务端后台执行，实时显示事件流（loop / tool / feedback / task_end）
- 危险动作弹出审批面板：`a` 批准、`r` 拒绝、`x` 中止、`m` 修改（修改暂为关闭面板）
- 斜杠指令：`/sessions`、`/session new|open|rename|close|delete`、`/config`（配置向导）、`/status`（当前 session/task/审批状态）、`/help`、`/abort`、`/pause`、`/continue`、`/exit`

> 需要真实终端（TTY）：ink 在非交互管道（如 `echo | kl tui`）下会提示 raw mode 不支持，请在交互式终端中运行。

## 分发命令

```bash
make install   # 本地可编辑安装（server 使用 pip editable，CLI 使用 npm install）
make ci        # CI 依赖安装（CLI 使用 npm ci）
make test      # 运行 server pytest 与 CLI vitest
make dev       # roadmap 占位，默认退出码 1
```

打包配置已就绪（Task 5.3）：

- server：`server/pyproject.toml`，`python -m build server` 产出 wheel/sdist，console 入口 `kl-server`
- CLI：`cli/package.json` 配置 `bin`/`files`/`prepack`，`npm pack` 只发布 `dist` 构建产物

实际发布（push 到 PyPI / npm）尚未执行，属后续规划。

## 目录结构

- `server/`：Python FastAPI 包 `kl-server`，模块 `kl_server`，Python >= 3.11
  - `api/`：应用工厂、REST 路由与 WebSocket
  - `config/`：配置模型、YAML loader、凭证存储（keyring 等后端）
  - `core/`：AgentLoop、守卫（ScopeFence/DangerClassifier/HITL）、沙箱、上下文、反馈、审计日志、会话/任务管理
  - `hooks/`、`mcp/`、`memory/`、`models/`、`plugins/`、`providers/`、`skills/`、`storage/`、`tools/`：对应扩展子系统
  - `tests/`：pytest 测试
- `cli/`：TypeScript Ink/Commander CLI（`@kl-code/cli`，Node >= 22）
  - `src/commands/`、`src/tui/`、`src/api/`：命令、TUI 屏、HTTP 客户端
  - `test/`：vitest 测试
- `examples/`：mock-LLM 机制演示脚本（守卫、反馈、上下文、工具错误）
- `docs/`：项目文档
- 根文件：`Makefile`、`README.md`、`SPEC.md`、`PLAN.md`、`SPEC_PROCESS.md`、`AGENT_LOG.md`、CI 配置

## 安全边界

- 服务仅绑定 `127.0.0.1:8700`，不对外网监听。
- 守护进程 token 存储在 `~/.kl/daemon.token`；HTTP API 中间件校验 `Authorization: Bearer <token>`。
- 命令执行受 `kl_server.core.guardrail`（ScopeFence、DangerClassifier、HITLManager）与 `kl_server.core.sandbox`（SandboxPolicy）约束。
- 审计日志由 `kl_server.core.event_logger` 写入，敏感字段（密钥、token、密码、私钥等）会被脱敏。
- 凭证通过 `kl_server.config.credentials`（keyring 等后端）管理，仓库不提交任何真实凭证。
- 守卫与服务端组装已在 bootstrap（Task 5.6）中接线；部署前仍需按 `SPEC.md` 完成最终安全审计。

## 关键配置

- Provider 注册默认使用 `mock`；可通过配置新增 openai-compatible 实例。
- 配置加载：`kl_server.config.loader.load_app_config`，配置模型 `kl_server.config.config.AppConfig`（YAML，`extra="forbid"`）。
- 凭证存储：`kl_server.config.credentials`（keyring 后端，含内存回退与 .env 支持）。
- 配置 YAML 由 `bootstrap.build_app_dependencies` 在服务启动时加载（Task 5.6 已接入）。CLI 的 provider/key 配置命令暂未写回该文件，见"已知限制"。

## 已知限制

- `kl tui` 尚未接线（组件已实现），`make dev` 仍为占位守卫，均按 roadmap 处理。
- `kl init` 依赖守护进程已运行，否则连接被拒（`ECONNREFUSED 127.0.0.1:8700`）而失败。
- `kl server start` 探测 python 需要能导入 uvicorn/fastapi/kl_server；若本机只有缺依赖的系统 python，请用项目 venv 手动启动。
- TUI 的 `/pause`、`/continue` 为任务状态标记（TaskManager 状态机）；运行中任务的真正挂起/恢复尚未实现。
- 服务端凭据库在 keyring 不可用时回退为内存存储（不持久化），初始化时会提示。
- WebUI、subagent 分派、远程部署与 Docker **不在** `SPEC.md`/`PLAN.md` 授权范围内，仓库不会承诺这些能力。
