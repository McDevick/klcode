# KL Code

> 原名：Simple Coding Agent

## 项目简介

**KL Code** 是一个本地 Coding Agent（编码智能体）：在已有代码库中用自然语言接任务，读取项目、修改文件、执行命令、跑测试，并基于客观反馈自我修正。

核心机制（agent 主循环、工具分发、治理、反馈、记忆、上下文管理）全部由项目自己的代码实现，不依赖现成 agent 编排框架；移除真实 LLM 后仍可通过确定性单元测试验证（mock provider）。

当前进度：核心框架 + 上下文重构 Phase 1–3 已实现并通过测试（server 500+ / cli 100+ 测试全绿）。

## 功能特性

- **AgentLoop 主循环**：context → LLM → 工具 → 反馈的固定循环；最大 20 轮 + 同类别失败重试预算降级信号
- **反馈闭环**：工具输出纯代码分类（成功/测试失败/构建失败/lint/类型/超时/工具错误/provider 错误），去重、截断、熵脱敏后回灌下一轮
- **上下文四层记忆系统**：
  - 规则层：用户指令沉淀 > 用户规则 > 项目规则（`.kl/rules.md` + `AGENTS.md`）> 默认
  - 状态层：task_plan（子任务 done/pending）、续接上下文（跨任务 outcome/files/next_step）
  - 事实层：记忆按 kind 配额 + 关键词相关注入；**用户指令沉淀**（note/任务描述中的约束、偏好、流程跨任务生效）
  - 轨迹层：历史分桶压缩（对话摘要 + 工具结果落盘引用 + 反馈去重）
- **治理**：ScopeFence 路径围栏、SandboxPolicy 命令策略（白/黑名单、环境变量裁剪、CPU/内存资源限制、fail-closed）、DangerClassifier 危险分级（按工具权限声明）、HITL 审批状态机、`governance_decision`/审批事件审计
- **工具系统**：17 个内置工具（文件/搜索/补丁/shell/git/测试/任务编排）+ 用户 Python 插件 + MCP 远程工具发现注册；工具声明权限/沙箱/超时；jsonschema 参数校验；大输出落盘引用
- **持久化**：SQLite（会话/任务/记忆/状态）+ append-only 脱敏审计日志 + AES 加密凭证库（keyring 优先）
- **TUI**：CommandRegistry 注册表（别名/参数 schema/状态门控）、双向状态门控、审批面板、会话/技能/MCP/模型/连接管理面板、/exit 运行中二次确认

## 环境要求

- Python >= 3.11
- Node.js >= 22，含 npm

## 全新机器快速开始

```bash
# 1. 获取代码
git clone <仓库地址> klcode
cd klcode

# 2. 安装依赖
make install            # = pip install -e "server[dev]" + cd cli && npm install
# Windows 无 make：
#   python -m pip install -e "server[dev]"
#   cd cli && npm install && cd ..

# 3. 准备 venv（关键：必须用项目 venv，不要用系统 python）
python -m venv .venv
.venv\Scripts\python.exe -m pip install -e "server[dev]"   # Windows
# .venv/bin/pip install -e "server[dev]"                   # Linux/macOS

# 4. 启动服务端（在项目根目录）
kl server start         # 自动探测 python 拉起 uvicorn；或手动：
.venv\Scripts\python.exe -m uvicorn kl_server.main:app --host 127.0.0.1 --port 8700 --timeout-graceful-shutdown 3

# 5. 初始化（服务端没跑会自动拉起）
kl init

# 6. 配置真实模型（默认 mock）
kl config provider add deepseek openai-compatible https://api.deepseek.com deepseek-v4-flash
kl config key set deepseek          # 隐藏输入，进系统钥匙串

# 7. 启动 TUI 提交任务（需要真实终端 TTY）
npm run tui
```

首次启动自动生成 `~/.kl/daemon.token` 和 `.kl/`（config.yaml、kl.db、audit.jsonl、memory.db）。缺少 config.yaml 也能启动，默认 provider 为 `mock`。

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

### 使用虚拟环境（venv）

> **必须用项目虚拟环境（venv），不要用系统 `python`**：系统 Python 可能未装依赖，或装有旧版本的 kl-server，会导致接口报错（如创建 session 返回 500）。

venv 是项目目录里的一个隔离 Python 环境，本项目的依赖（fastapi / uvicorn / aiosqlite 等）都已装在其中。本仓库开发 venv 位于 `.superpowers\sdd\PLAN\venv\`。

#### 方式一：激活 venv 后使用（推荐）

在 PowerShell 中激活（激活后**当前终端**的提示符会变成 `(venv) PS ...>`，之后 `python` 命令就指向 venv）：

```powershell
& E:\projects\SimpleCodingAgent\.superpowers\sdd\PLAN\venv\Scripts\Activate.ps1
```

如果报错 `...因为在此系统上禁止运行脚本...`，先放开执行策略（仅对当前用户生效，执行一次即可）：

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

然后**重新执行激活命令**。验证是否激活成功：

```powershell
Get-Command python
# 路径应显示 ...\.superpowers\sdd\PLAN\venv\Scripts\python.exe 而不是系统 Python
```

激活后即可直接使用 `python` 启动服务端：

```powershell
python -m uvicorn kl_server.main:app --host 127.0.0.1 --port 8700 --timeout-graceful-shutdown 3
```

> 注意：激活只对**当前终端窗口**生效，新开终端需要重新激活；退出环境用 `deactivate`。

#### 方式二：不激活，直接调用 venv 的 python.exe（最简单，无需任何前置）

```powershell
E:\projects\SimpleCodingAgent\.superpowers\sdd\PLAN\venv\Scripts\python.exe -m uvicorn kl_server.main:app --host 127.0.0.1 --port 8700 --timeout-graceful-shutdown 3
```

复制整行运行即可，不需要激活、不需要执行策略设置。

#### 如果还没有 venv，创建并安装依赖

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -e "server[dev]"
```

### 启动服务端（daemon）

venv 就绪后（方式一或方式二均可），启动服务端：

```powershell
# 方式二（不激活，直接调用 venv 的 python.exe）：
E:\projects\SimpleCodingAgent\.superpowers\sdd\PLAN\venv\Scripts\python.exe -m uvicorn kl_server.main:app --host 127.0.0.1 --port 8700 --timeout-graceful-shutdown 3
# 方式一（已激活 venv）：
python -m uvicorn kl_server.main:app --host 127.0.0.1 --port 8700 --timeout-graceful-shutdown 3
# 或已安装 server[dev] 后使用 console 入口：
kl-server
```

`make dev`（roadmap，尚未可用）：当前是占位守卫，输出提示并以退出码 1 结束（待接线为"同时启动服务端与 TUI"）。

### CLI

CLI 程序名为 `kl`（`cli/src/main.ts` 中 `program.name('kl')`）。已配置 `bin` 与 esbuild 构建（`npm run build` → `cli/dist/main.js`）。开发期可从 `cli/` 目录直接运行：

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

- `kl server start|stop|status`：管理本地守护进程。`start` 自动探测可用的 python（venv 优先，其次 `python`/`python3`/`py`，要求能导入 uvicorn/fastapi/kl_server），用探测到的 python 以 `-m uvicorn kl_server.main:app --host 127.0.0.1 --port 8700 --timeout-graceful-shutdown 3` 拉起服务，PID 写入 `~/.kl/daemon.pid`；无可用 python 时返回明确错误提示。
- `kl init`：查询初始化状态。**服务端未运行时自动拉起 daemon**（复用 server start 探测/拉起逻辑，轮询 /health 就绪后重试）——全新机器一条命令即可冷启动；仅网络错误触发自动启动，HTTP 类错误原样报出。
- `kl run <task>`：提交一次性任务。自动创建 session（workspace 为当前目录）后提交，任务在服务端后台执行。
- `kl config <area> <action> ...`：管理 provider 与 key（如 `kl config provider list`、`kl config key show <ref>`）。`kl config key set` 写入服务端凭据库（keyring 优先，AES 加密文件回退）；`kl config provider add` 注册 provider 并写回 `.kl/config.yaml`（重启后仍生效）。
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
- 危险动作弹出审批菜单：方向键选择 approve/reject/abort，Enter 确认；快捷键 `a`/`r`/`x`
- 滚轮（需 `/mouse`）、方向键按行连续滚动，PageUp/PageDown 半屏滚动
- 斜杠指令（17 个，经 CommandRegistry 注册）：`/session`（会话管理）、`/skills`、`/mcp`、`/config`、`/connect`、`/status`、`/model`、`/context`、`/compact`、`/help`、`/abort`、`/note`（给任务追加说明）、`/pause`、`/continue`、`/debug`、`/mouse`、`/exit`
- **双向状态门控**：/session、/config、/connect、/compact 任务运行时禁用；/abort、/note、/pause、/continue 无任务时禁用
- **/exit 运行中二次确认**：任务运行时第一次输入提示"再次输入 /exit 确认退出"，第二次才退出
- 参数错误显示该指令的用法（注册表生成式提示）

斜杠命令菜单和配置向导会停靠在消息区下方的固定面板中，不覆盖已有对话；输入区始终保留在面板下方。

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

CI 包含两个 job：`unit-test`（make ci + make test）与 `dist-check`（wheel/sdist 构建 + 包内容断言 + cli build + --help 可运行性检查）。

实际发布（push 到 PyPI / npm）尚未执行，属后续规划。

## 目录结构

- `server/`：Python FastAPI 包 `kl-server`，模块 `kl_server`，Python >= 3.11
  - `api/`：应用工厂、REST 路由与 WebSocket
  - `config/`：配置模型、YAML loader、凭证存储（keyring/AES 加密文件）
  - `core/`：AgentLoop、守卫（ScopeFence/DangerClassifier/HITL）、沙箱（SandboxPolicy）、上下文（ContextAssembler/分桶压缩/关键词提取）、反馈、指令沉淀、审计日志、会话/任务管理
  - `hooks/`、`mcp/`、`memory/`、`models/`、`plugins/`、`providers/`、`skills/`、`storage/`、`tools/`：对应扩展子系统
  - `tests/`：pytest 测试
- `cli/`：TypeScript Ink/Commander CLI（`@kl-code/cli`，Node >= 22）
  - `src/commands/`、`src/tui/`（含 commands.ts 指令注册表）、`src/api/`：命令、TUI 屏、HTTP 客户端
  - `test/`：vitest 测试
- `examples/`：mock-LLM 机制演示脚本（守卫、反馈、上下文、工具错误）
- `docs/`：项目文档（SPEC 承诺跟踪 `promise_state.md`、上下文重构方案 `context-redesign.md`）
- 根文件：`Makefile`、`README.md`、`SPEC.md`、`PLAN.md`、`SPEC_PROCESS.md`、`AGENT_LOG.md`、CI 配置

## 安全边界

- 服务仅绑定 `127.0.0.1:8700`，不对外网监听。
- 守护进程 token 存储在 `~/.kl/daemon.token`；HTTP API 中间件校验 `Authorization: Bearer <token>`。
- 命令执行受 `kl_server.core.guardrail`（ScopeFence、DangerClassifier、HITLManager）与 `kl_server.core.sandbox`（SandboxPolicy：白/黑名单、二进制混淆防护、环境变量裁剪、CPU/内存资源限制、配置损坏时 fail-closed）约束。
- 危险等级按工具权限声明分级（`destructive` / `unmanaged_escalation`），新插件工具声明权限即自动受控。
- 审计日志由 `kl_server.core.event_logger` 写入（append-only），敏感字段脱敏；治理决策、审批请求/完成均有独立审计事件。
- hook payload 经 `redact_payload` 脱敏后外发。
- 凭证通过 `kl_server.config.credentials` 管理（keyring 优先 → AES 加密文件回退），仓库不提交任何真实凭证。
- 部署前仍需按 `SPEC.md` 完成最终安全审计。

## 关键配置

- Provider 注册默认使用 `mock`；可通过配置新增 openai-compatible 实例（加载器含 DeepSeek 预设，config.yaml 留空也会自动合并）。
- 配置加载：`kl_server.config.loader.load_app_config`，配置模型 `kl_server.config.config.AppConfig`（YAML，`extra="forbid"`，含 `sandbox` 配置节）。
- 凭证存储：`kl_server.config.credentials`（keyring 后端，AES 加密文件回退，支持 .env）。
- 配置 YAML 由 `bootstrap.build_app_dependencies` 在服务启动时加载（含 fail-closed 兜底：配置损坏时以 deny_all 沙箱启动并暴露错误）。

## 已知限制

- `make dev` 仍为占位守卫，按 roadmap 处理。
- `kl server start` 探测 python 需要能导入 uvicorn/fastapi/kl_server；若本机只有缺依赖的系统 python，请用项目 venv 手动启动。
- 服务端凭据库在 keyring 与加密文件都不可用时才回退为内存存储（不持久化），初始化时会提示。
- 任务在 Git 仓库中直接修改当前分支文件（自动建任务分支未实现，回滚靠手动 git 还原）；非 Git 目录任务开始时做快照，但快照不自动回滚。
- 审批请求无超时机制：无人值守时任务会一直等待审批。
- WebUI、subagent 分派、远程部署与 Docker **不在** `SPEC.md`/`PLAN.md` 授权范围内，仓库不会承诺这些能力。
