# KL Code

> 原名：Simple Coding Agent

## 项目简介

**KL Code** 是一个 Coding Agent（编码智能体）项目。

本仓库目录名仍沿用 `SimpleCodingAgent`，但项目正式名称定为 **KL Code**，后续文档、命名、标识统一使用该名称。

当前进度：Python 侧已完成核心框架（模型、Provider、AgentLoop、工具、存储、守卫、MCP/插件、内存与上下文），CLI 脚手架可用；服务端完整组装与 CLI TUI 仍处于 roadmap 阶段（见“已知限制”）。

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
python -m pytest server/tests -q --pyargs
cd cli
npm test
```

开发启动（roadmap，尚未可用）：

```bash
make dev
```

`make dev` 当前是占位守卫：仅输出 `make dev is not available until server main and cli tui entrypoints exist` 并以退出码 1 结束，直到 `kl_server.main` 与 CLI TUI 入口完成。

### CLI

CLI 计划程序名为 `kl`（见 `cli/src/main.ts` 中 `program.name('kl')`）。当前尚未发布可执行文件，也没有 `bin` 入口，开发期从 `cli/` 目录运行：

```powershell
cd cli
npx tsx src/main.ts --help
```

已接线的子命令（示例均以 `kl` 表示最终程序名）：

- `kl server start|stop|status`：管理本地守护进程。`start` 通过 `python -m uvicorn kl_server.main:app --host 127.0.0.1 --port 8700` 拉起服务，PID 写入 `~/.kl/daemon.pid`。
- `kl init`：查询初始化状态。需要守护进程已运行并能访问 `http://127.0.0.1:8700`，否则连接被拒而失败；请先执行 `kl server start`。
- `kl run <task>`：提交一次性任务。
- `kl config <area> <action> ...`：管理 provider 与 key（如 `kl config provider list`、`kl config key show <ref>`）。
- `kl tui`：**尚未接线**，`cli/src/main.ts` 中没有 `tui` 子命令。当前运行会以退出码 1 返回 `error: unknown command 'tui'`，属于 roadmap。

## 分发命令

```bash
make install   # 本地可编辑安装（server 使用 pip editable，CLI 使用 npm install）
make ci        # CI 依赖安装（CLI 使用 npm ci）
make test      # 运行 server pytest 与 CLI vitest
make dev       # roadmap 占位，默认退出码 1
```

当前没有打包发布命令：CLI 未提供 `bin`/构建产物，server 未配置发布目标，分发能力属于后续规划。

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
- 上述守卫与真实服务组装尚未完全接线，属于待集成能力；部署前需按 `SPEC.md` 完成最终组合并重新审计。

## 关键配置

- Provider 注册默认使用 `mock`；可通过配置新增 openai-compatible 实例。
- 配置加载：`kl_server.config.loader.load_app_config`，配置模型 `kl_server.config.config.AppConfig`（YAML，`extra="forbid"`）。
- 凭证存储：`kl_server.config.credentials`（keyring 后端，含内存回退与 .env 支持）。
- 配置 YAML 路径的读写尚未接入服务端运行流程（属于 Server Bootstrap/Task 5.6），当前以模块级 API 与测试契约为准。

## 已知限制

- `make dev` 与 `kl tui` 尚未接线，均按 roadmap 处理。
- `kl init` 依赖守护进程已运行；守护进程未启动时，它会直接因连接被拒（`ECONNREFUSED 127.0.0.1:8700`）而失败，前置条件为 `kl server start`。
- 服务端 bootstrap 与真实组合（SessionManager/TaskManager/配置装配）尚未激活，属 Task 5.6。
- WebUI、subagent 分派、远程部署与 Docker **不在** `SPEC.md`/`PLAN.md` 授权范围内，仓库不会承诺这些能力。
