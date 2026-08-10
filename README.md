# KL Code

> 原名：Simple Coding Agent

KL Code 是一个本地 Coding Agent：在已有代码库中用自然语言接任务，读取项目、修改文件、执行命令、跑测试，并基于客观反馈自我修正。

核心机制（agent 主循环、工具分发、治理、反馈、记忆、上下文管理）全部由项目自己的代码实现，不依赖现成 agent 编排框架；移除真实 LLM 后仍可通过 mock provider 做确定性验证。

当前版本：`v0.1.0`。已发布 npm 包 `kl-code-cli`、PyPI 包 `kl-server` 与 GitHub Release。

## 功能特性

- **AgentLoop 主循环**：context → LLM → 工具 → 反馈的固定循环
- **反馈闭环**：工具输出分类、去重、截断、脱敏后回灌下一轮
- **上下文四层记忆系统**：
  - 规则层：用户指令沉淀 > 全局用户规则 > 项目规则 > 默认
  - 状态层：任务计划、续接上下文
  - 事实层：记忆配额 + 关键词相关注入
  - 轨迹层：历史分桶压缩 + 大输出落盘引用
- **治理**：ScopeFence 路径围栏、SandboxPolicy 命令策略、危险分级、HITL 审批状态机、治理/审批审计
- **工具系统**：内置文件/搜索/patch/shell/git/测试/任务/输出读取工具 + 用户 Python 插件 + MCP 远程工具
- **持久化**：SQLite 会话/任务/记忆 + append-only 脱敏审计日志 + 加密凭证库
- **TUI**：命令菜单、会话管理、skill 列表、MCP 管理、模型切换、API 连接配置、审批面板、历史回放

## 环境要求

- Python `>= 3.11`
- Node.js `>= 22`
- npm

## 发布后快速开始

这是正式发布包最常用的启动方式。

### Windows / macOS / Linux

```bash
npm install -g kl-code-cli

kl init
kl tui
```

说明：

- `npm install -g kl-code-cli` 会注册全局 `kl` 命令。
- 首次运行 `kl init` / `kl tui` 时，如果没有可用的 `kl-server`，CLI 会自动创建 `~/.kl/venv` 并从 PyPI 安装对应版本的 `kl-server`。
- 也可以手动安装 server：

```bash
pip install kl-server
```

- `kl-server` 只提供服务端命令，不注册 `kl`。

### 安装前检查

请确保环境中有可运行的 npm 和 pip：

```powershell
npm --version
python -m pip --version
```

如果命令不可用，请先安装 Node.js `>=22` 和 Python `>=3.11`。

### 无法自动拉起 server 时

如果 `kl tui` 多次重启后仍然无法自动拉起服务端，请手动启动：

```powershell
python -m pip install kl-server
kl server start
kl tui
```

也可以直接使用 uvicorn 启动：

```powershell
python -m uvicorn kl_server.main:app --host 127.0.0.1 --port 8700 --timeout-graceful-shutdown 3
```

### 如果 `kl` 命令找不到

检查 npm 全局 bin 是否在 PATH：

```powershell
npm config get prefix
npm prefix -g
```

Windows 常见全局 bin 目录：

```text
%APPDATA%\npm
```

Linux/macOS 常见：

```text
~/.npm-global/bin
/usr/local/bin
```

## 源码运行

### 克隆并安装

```bash
git clone <仓库地址> klcode
cd klcode
```

创建虚拟环境并安装依赖：

```bash
python -m venv .venv
```

Windows：

```powershell
.\.venv\Scripts\python.exe -m pip install -e "server[dev]"
cd cli
npm install
cd ..
```

Linux/macOS：

```bash
.venv/bin/python -m pip install -e "server[dev]"
cd cli
npm install
cd ..
```

有 `make` 的环境也可以直接执行：

```bash
make install
```

### 构建 CLI

```bash
cd cli
npm run build
cd ..
```

### 启动

从源码目录启动 TUI：

```bash
node cli/dist/main.js init
node cli/dist/main.js tui
```

或注册源码版 `kl`：

```bash
cd cli
npm link
cd ..

kl init
kl tui
```

手动启动服务端：

```bash
.venv\Scripts\python.exe -m uvicorn kl_server.main:app --host 127.0.0.1 --port 8700 --timeout-graceful-shutdown 3
```

Linux/macOS 对应：

```bash
.venv/bin/python -m uvicorn kl_server.main:app --host 127.0.0.1 --port 8700 --timeout-graceful-shutdown 3
```

## 首次运行

首次启动会自动生成全局目录：

```text
~/.kl/
  config.yaml
  kl.db
  memory.db
  audit.jsonl
  daemon.token
  venv/
  skills/
  tools/
  tool_outputs/
```

- 配置统一读取 `~/.kl/config.yaml`，不再读取项目目录下的 `.kl/config.yaml`。
- skill 位于 `~/.kl/skills/<name>/SKILL.md`。
- 用户 Python 插件位于 `~/.kl/tools/`。
- 大输出默认写入 `~/.kl/tool_outputs/`。

默认 provider 是 `deepseek`。首次使用请先在 TUI 中执行 `/connect` 配置 API Key，也可以使用 `/model` 切换到 `mock` 无 key 试跑。

## 常用命令

```text
kl init                 初始化并准备服务端
kl tui                  启动 TUI
kl run "任务描述"        提交一次性任务
kl server start|stop|status
kl config provider list
kl config key set <ref>
```

TUI 内常用指令：

```text
/connect   配置 API Key
/model     切换模型
/skills    查看 skill
/mcp       管理 MCP server
/session   会话管理
/context   查看上下文状态
/compact   手动压缩上下文
/note      给任务追加说明
/abort     中止任务
/pause     暂停任务
/continue  继续任务
/exit      退出
```

## 配置

示例配置：

```text
examples/config.example.yaml
```

可复制为：

```text
~/.kl/config.yaml
```

关键配置说明：

- `default_provider` / `default_model`：默认 provider 与模型
- `providers`：provider 的 base_url、模型列表、credential_ref
- `mcp`：MCP server 配置
- `sandbox`：命令允许/拒绝列表、超时、资源限制
- `guardrail.approval_timeout_seconds`：审批超时，默认 300 秒
- `storage.tool_outputs_dir`：大输出目录，默认 `~/.kl/tool_outputs`

配置加载逻辑位于 `server/kl_server/config/loader.py`，配置模型位于 `server/kl_server/config/config.py`。

## Skill

Skill 文件位于：

```text
~/.kl/skills/<name>/SKILL.md
```

推荐格式：

```markdown
---
name: leetcode
description: 算法题解题流程
keywords: [leetcode, 算法, cpp]
when_to_use: 用户要求解决算法题时
summary: 先分析题目结构，再编码并用测试验证。
always_on: false
---

## Workflow
...
```

- 新增/修改 skill 不需要重启后端。
- `/skills` 只展示 skill 名称。
- agent 可以通过 `read_skill(name)` 获取完整内容。
- 大型 skill 可以通过 `read_skill(name, section=...)` 分节读取。

## MCP

MCP server 在全局配置中声明：

```yaml
mcp:
  filesystem:
    command: npx
    args:
      - "-y"
      - "@modelcontextprotocol/server-filesystem"
```

- `/mcp` 可以查看、刷新、删除 MCP server。
- filesystem MCP 会自动把当前 session 的 workspace 追加为允许目录。
- 切换 TUI 工作目录不需要重启服务端。
- 直接修改 `~/.kl/config.yaml` 中的 MCP 配置后，需要刷新 `/mcp` 或重启服务端。

## 演示

仓库内 demo 位于 `examples/`，全部使用 mock LLM，不需要真实 API Key：

```text
examples/context_demo.py
examples/feedback_demo.py
examples/guardrail_demo.py
examples/tool_error_demo.py
examples/skill_demo.py
examples/mcp_demo.py
```

运行单个 demo：

```bash
python examples/context_demo.py
python examples/feedback_demo.py
python examples/skill_demo.py
python examples/mcp_demo.py
```

运行全部 demo：

```powershell
Get-ChildItem examples\*_demo.py | ForEach-Object { python $_.FullName }
```

## 目录结构

```text
server/     Python FastAPI 服务端 kl-server
cli/        TypeScript Ink/Commander CLI kl-code-cli
examples/   mock-LLM 演示脚本
docs/       设计、SPEC、发布与风险文档
```

## 开发与测试

```bash
make ci        # 安装依赖
make test      # 服务端测试 + CLI 测试
make dev       # 构建 CLI 并启动 TUI
```

等价命令：

```bash
python -m pytest server/tests -q
cd cli && npm test
cd cli && npx tsc --noEmit
```

当前基线：

- Server：`555 passed, 1 skipped`
- CLI：`124 passed`
- TypeScript：通过

## 发布

- npm：`kl-code-cli`
- PyPI：`kl-server`
- GitHub Release：`v0.1.0`

Release workflow 位于：

```text
.github/workflows/release.yml
```

推送 `v<version>` tag 后会自动：

- 运行测试
- 构建 server wheel/sdist
- 构建 CLI tarball
- 发布 npm 与 PyPI
- 创建 GitHub Release 并附带资产

发布详情见 `RELEASE_NOTES.md` 和 `docs/release-package.md`。

## 安全边界

- 服务仅绑定 `127.0.0.1:8700`
- daemon token 存储在 `~/.kl/daemon.token`
- HTTP API 校验 `Authorization: Bearer <token>`
- 命令执行受 Guardrail 与 SandboxPolicy 约束
- 危险工具按权限声明分级
- 审计日志 append-only 且敏感字段脱敏
- hook payload 自动脱敏
- 凭证优先 keyring，回退 AES 加密文件

## 注意事项

- Skill 文件无需重启后端。
- 用户插件 `~/.kl/tools/` 在服务端启动时加载，新增插件需要重启。
- MCP 配置文件修改后需要刷新或重启服务端。
- 代码改动需要重启服务端。
- filesystem MCP 自动跟随 workspace。

## 已知限制

- `run_command` 不是 OS 级沙箱：当前默认 `sandbox.allow` 为空时，除 deny 列表外可执行任意本机命令，也能读写 workspace 外文件。不建议在不可信目录或多人共享环境中运行。
- 凭据保护存在本地文件读取风险：keyring 不可用时，AES 加密回退的主密码与密文同存于 `~/.kl`；配置也允许明文 `api_key`。API Key 仍建议优先通过 `/connect` 或 keyring 保存。
- 上下文 token 预算：当前使用估算，没有模型真实 tokenizer/usage，也没有循环级 token 硬停止；长任务主要靠 `max_iterations` 兜底。
- Hook 执行同步阻塞：慢 hook 可能阻塞其他任务和 WS 事件。
- 快照/Git 边界：非 Git 快照失败时任务仍继续；Git 模式不自动创建任务分支。
- `kl server start` 探测 Python 需要能导入 `uvicorn`、`fastapi`、`websockets`、`kl_server`。
- 审批请求默认 300 秒超时，超时自动拒绝。
- WebUI、subagent 分派、远程部署与 Docker 不在当前授权范围内。