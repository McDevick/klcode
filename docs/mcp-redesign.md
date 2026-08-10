# KL Code MCP workspace-aware redesign

> 状态：已实现（2026-08-10）
> 范围：McpAdapter / McpRemoteTool / MCP transport 生命周期
> 关联：docs/server-redesign.md（全局 daemon）、docs/promise_state.md（SPEC §3.9）
> 触发：官方 filesystem MCP 在全局 daemon 下 allowed directories 为空，且 MCP 目录不跟随 TUI session.workspace

## 1. 背景与问题

当前架构下，MCP server 的配置是全局的，服务端进程是全局 daemon，但 session.workspace 是由 TUI 启动目录决定的。两者没有联动：

```text
~/.kl/config.yaml
  mcp.filesystem.args
    -> 启动 @modelcontextprotocol/server-filesystem
    -> allowed directories 固定为进程启动参数

session.workspace
  -> TUI 当前目录
  -> 与 MCP server 启动参数无关
```

官方 filesystem MCP server 的权限模型是“进程启动时通过位置参数传入允许目录”，不是“自动跟随当前目录”。当前全局配置中常见写法：

```yaml
mcp:
  filesystem:
    command: npx
    args:
      - "-y"
      - "@modelcontextprotocol/server-filesystem"
```

这个配置会启动一个 allowed directories 为空的 filesystem MCP，导致：

- `mcp_filesystem_list_allowed_directories` 返回空列表；
- 任何 `read_file` / `write_file` / `edit_file` 都报 `path outside allowed`；
- 即使 daemon 是在 TUI 所在目录启动的，也不解决问题，因为 MCP 读的是 `args`，不是 daemon cwd。

## 2. 目标

1. filesystem MCP 的允许目录跟随当前会话的 `session.workspace`。
2. MCP 配置仍然全局化，不引入项目级 MCP 配置。
3. 非 filesystem MCP server 保持现有单进程行为。
4. 每个 workspace 的 MCP 子进程有明确生命周期，不产生孤儿进程。
5. 不通过放宽到整个磁盘/用户目录来绕过权限。

## 3. 明确不做

- 不做项目级 MCP 配置（与 server-redesign 的纯全局配置原则冲突）。
- 不默认允许用户主目录、盘符根目录或整个文件系统。
- 不改变非 filesystem MCP 的配置语义。
- 不要求用户为每个 TUI 目录手动修改 `args`。
- 不在本阶段引入每会话独占 MCP server；粒度做到 workspace 即可。

## 4. 架构

### 4.1 workspace-aware transport

把 `McpAdapter` 的 transport 缓存从“每个 server 一个”升级为“每个 `server + workspace` 一个”：

```text
_transports:
  ("filesystem", "E:\projects\SomeDome")  -> npx server-filesystem E:\projects\SomeDome
  ("filesystem", "E:\projects\Other")     -> npx server-filesystem E:\projects\Other
  ("demo", "")                            -> 非 filesystem server，保持单进程
```

调用链：

```text
AgentLoop
  -> ToolContext(workspace=session.workspace)
  -> McpRemoteTool.execute(args, ctx)
  -> McpAdapter.tool(server, name, args, workspace=ctx.workspace)
  -> 选择/创建对应 workspace 的 McpTransport
```

`McpAdapter.tool()` 新增可选 `workspace` 参数：

```python
async def tool(
    self,
    server: str,
    name: str,
    args: dict,
    workspace: str | None = None,
) -> ToolResult:
    ...
    transport = self._get_transport(server, workspace)
```

`McpRemoteTool.execute()` 不再只传 `server/name/args`，而是把当前 `ToolContext.workspace` 一起传下去：

```python
async def execute(self, args: dict, ctx: ToolContext) -> ToolResult:
    return await self.adapter.tool(
        self.server,
        self.remote_name,
        args,
        workspace=ctx.workspace,
    )
```

### 4.2 filesystem 参数生成

只对识别为官方 filesystem MCP 的 stdio server 做 workspace 注入。识别依据为 command/args 中包含 `@modelcontextprotocol/server-filesystem`。

规则：

```text
显式目录为空     -> args += [session.workspace]
显式目录非空     -> 保留显式目录；若 workspace 不在其中则追加 workspace
```

workspace 在追加前做 `Path.resolve()` 归一化，避免相对路径、大小写和尾部分隔符造成重复启动。

### 4.3 工具发现与调用分离

工具列表（schema/名称/描述）不依赖 workspace，因此发现阶段可以复用无 workspace 的 probe transport：

```text
register_mcp_tools / refresh
  -> adapter.list_tools(server)
  -> 仅用于发现工具，不与具体 workspace 绑定

实际工具调用
  -> adapter.tool(..., workspace=session.workspace)
  -> 使用 workspace transport
```

这样不会出现“启动时用空目录发现了工具，调用时也沿用空目录”的问题。

## 5. 生命周期

### 5.1 创建

- 首次调用某 workspace 的 filesystem 工具时创建对应 transport。
- 同 workspace 的多个 session/任务共享同一个 transport。
- 非 filesystem server 仍按 server 维度创建。

### 5.2 释放

- `McpAdapter.close()`：关闭全部 transport，服务端退出/重启时使用。
- session 删除：清理该 session.workspace 下不再被其他 session 使用的 filesystem transport。
- MCP refresh/remove：关闭该 server 的全部 transport，确保新配置立即生效。

### 5.3 可选的空闲回收

第一阶段可以先只做 session 删除和服务端关闭时回收。若担心长期 daemon 累积多个 workspace 子进程，后续增加 TTL：

```text
transport 最后使用时间 + N 分钟无访问 -> close
```

TTL 不作为第一阶段阻塞项。

## 6. 边界场景

| 场景 | 行为 |
|---|---|
| 在 `SomeDome` 打开 TUI | filesystem MCP 允许 `SomeDome` |
| 同一 daemon 下切到 `Other` 新 session | 新建 `Other` 的 filesystem MCP |
| 两个 session 使用同一 workspace | 复用同一 filesystem MCP |
| 配置里已有显式目录 | 保留显式目录，并追加当前 workspace |
| 非 filesystem MCP | 不注入 workspace，保持原行为 |
| session 删除 | 若无其他 session 使用该 workspace，关闭对应 transport |
| MCP refresh/remove | 关闭该 server 全部 transport，重新发现/删除工具 |
| daemon 重启 | 所有 transport 关闭，工具调用时按 workspace 重新创建 |

## 7. 安全边界

当前 MCP 远程工具权限是 `["mcp"]`，不会像内置文件工具一样被 ScopeFence 按 `path` 拦截。因此：

- filesystem MCP 必须在 MCP server 进程层限制 allowed directories；
- 默认只允许当前 workspace，避免 MCP 成为绕过内置文件工具工作区边界的通道；
- 不提供“自动允许用户目录/盘符根目录”的默认行为；
- 显式配置多个目录是用户主动信任行为，文档中应保留说明。

## 8. 实现要点

| 组件 | 改动 |
|---|---|
| `server/kl_server/mcp/adapter.py` | transport 缓存改为 `(server, workspace)`；`tool()` 接收 workspace；新增 `release_workspace()`/`release_server()`；filesystem 参数生成 |
| `server/kl_server/extensions.py` | `McpRemoteTool.execute()` 将 `ctx.workspace` 传给 adapter |
| `server/kl_server/api/routes.py` | session 删除时调用 `mcp.release_workspace()`；MCP refresh/remove 时调用 `mcp.release_server()` |
| `server/tests/test_mcp_adapter.py` | 新增 workspace cache、filesystem args、release 测试 |
| `server/tests/test_extensions.py` | 验证 MCP tool 调用携带 workspace |
| `server/tests/test_routes.py` | 验证 session 删除和 MCP refresh 会释放 transport |
| `docs/release-test.md` | 增加“filesystem MCP 跟随 TUI 目录”手动验收项 |

## 9. 被拒绝的方案

- **配置里写死当前目录**：只解决一次，切目录后再次失败。
- **allowed directories 设为盘符根目录**：能“到处可用”，但 MCP 没有内置路径守卫，风险过高。
- **每个 session 一个 MCP server**：进程数量与 session 数量挂钩，浪费资源；workspace 粒度足够。
- **每次调用前动态修改 filesystem server 配置**：官方 server 的 allowed directories 只在启动时生效，动态修改不可靠。
- **项目级 MCP 配置**：违反当前“配置纯全局、项目上下文 = workspace”的设计。

## 10. 验收

### 自动测试

```bash
python -m pytest server/tests -q
cd cli && npm test
```

### 手动验收

```text
1. 在 E:\projects\SomeDome 打开 kl tui
2. 调用 mcp_filesystem_list_allowed_directories
   -> 应包含 E:\projects\SomeDome
3. 切换到另一个目录的新 session
4. 再次调用 list_allowed_directories
   -> 应包含新目录，且不影响旧 workspace
5. 删除旧 session 后检查 MCP 子进程被释放
```
