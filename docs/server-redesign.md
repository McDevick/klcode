# KL Code 服务端生命周期重设计（daemon-lifecycle）

> 状态：设计待批准（2026-08-08）
> 范围：kl server start / kl tui / kl run / kl init 与服务端 daemon 的生命周期管理
> 关联：docs/context-redesign.md（上下文重构）、docs/promise_state.md（SPEC 跟踪）

## 1. 动机

当前 daemon 生命周期存在三个问题：

1. **`kl tui` / `kl run` 不自动拉起服务端**——TUI 打开后离线报错（"会话创建失败"），用户需手动 `kl server start` 再重开 TUI；与 `kl init`（已修：自动拉起）不对称
2. **服务端只能手动长期常驻**——常驻进程需要用户管理（启动/停止/自启），且易积累无人值守的挂起审批、版本更新后旧 daemon 跑旧代码
3. **stale PID 陷阱**——进程死了但 PID 文件残留时，`kl server start` 报 "already running" 但服务永远起不来
4. **配置与数据依赖 daemon cwd**——从任意目录自动拉起时，`.kl/`（config.yaml/kl.db/audit.jsonl）跟着触发目录走：配置漂移、会话/记忆碎片化（"记住用户说的话"失效）

## 2. 设计原则

**生命周期归属 = 启动方式**：

```
用户手动 kl server start   → 来源 manual → 用户自己管理（kl server stop 关闭）
自动拉起（tui/run/init 触发）→ 来源 auto   → 空闲自动回收（用完自己消失）
```

- 手动起的进程是用户资产，永不自动回收
- 自动拉起的是"借来的"，任务不需要时自己走
- 用户对任何来源的进程都有管理权（kl server stop 随时可停）

## 3. 架构

### 3.1 来源标记

```
~/.kl/daemon.json: { "pid": 12345, "source": "manual" | "auto", "started_at": "..." }
拉起 uvicorn 时传环境变量 KL_DAEMON_SOURCE=auto
服务端 lifespan 读取 → 决定是否启用空闲回收
```

### 3.2 空闲回收（仅 auto 来源）

```
auto 来源 + 无运行中任务 + 无 WS 连接 + 空闲 N 分钟 → 优雅退出
```

- **运行中任务保活**：用户跑长任务关了 TUI，进程必须活着（后台执行承诺）
- **WS 连接保活**：TUI 开着就是"在用"，**与用户是否操作无关**——晾着的 TUI 也有长连接，不回收
- **回收宽限期**：空闲计时从 WS 断开瞬间开始——断开后 N 分钟内有新连接（TUI 重连成功）即取消回收
- 任务结束才开始计空闲
- 优雅退出：uvicorn graceful shutdown（已有 3s 缓冲），状态全持久化（SQLite/审计/续接上下文），零损失

### 3.3 手动 start = 接管（防来源冲突）

```
kl server start 分支：
  PID 不存在                          → 启动 manual
  PID 存在 + source=manual            → "server already running"
  PID 存在 + source=auto：
      ├─ auto 无运行中任务 → 优雅停掉 auto → 启动 manual（接管）
      └─ auto 有运行中任务   → 拒绝接管 + 明确提示
           "自动拉起的服务端正在执行任务 tX，请等任务结束或 /abort 后再手动启动"
```

语义闭环：用户任何手动 start 最终得到"用户管理"的进程；auto 进程被接管或回收，不会残留。

### 3.4 stale PID 探测

`kl server start` 读 PID 后先验证进程存活（`process.kill(pid, 0)` 探测）：
- 存活 → 按 3.3 分支处理
- 已死 → 清理 PID 文件 → 正常启动（杜绝 "already running 但服务不存在"）

### 3.5 配置与数据路径全局化

**原则：daemon 进程跑在哪无所谓，配置与数据必须全局统一。**

所有数据路径显式指向全局家目录（不依赖 daemon cwd）：

```
~/.kl/config.yaml     ← 全局配置（唯一来源：provider/key/模型/沙箱）
~/.kl/kl.db           ← 全局数据库（会话/任务/记忆/指令沉淀）
~/.kl/audit.jsonl     ← 全局审计日志
~/.kl/daemon.token    ← 已有 ✓
~/.kl/daemon.pid      ← 已有 ✓
```

**纯全局配置，无项目级配置**：
- 不读取/不合并任何项目目录下的配置文件（项目 `.kl/config.yaml` 不再生效）
- 不做项目级初始化（无 /init 类动作）——项目差异不靠配置表达
- **项目上下文 = TUI 工作目录**（session.workspace）：用户在哪开 TUI，agent 就在哪干活，配置始终是全局那份

**迁移注意**：现有项目 `.kl/config.yaml` 中的配置（provider/key 引用等）需手动搬至 `~/.kl/config.yaml`——loader 改动后项目配置不再被读取，README 注明。

**推论（跨项目记忆）**：数据库全局化后，记忆/会话/指令沉淀跨项目统一——用户在 A 项目的偏好（如"别动 README"）沉淀进全局库，在 B 项目开 TUI 依然生效。"记住用户说的话"升级为跨项目记忆。

**待讨论**：环境解耦方案（全局自举 venv / 其他）——见 §9。

## 4. 边界场景

| 场景 | 行为 |
|---|---|
| auto 进程跑长任务中 | 保活，任务结束计空闲 |
| auto 进程上 TUI 一直开着（含晾着不操作） | 保活（WS 连接与操作无关） |
| WS 断连（网络抖动/休眠唤醒） | 空闲计时开始；TUI 重连成功即取消回收；TUI 无重连则 N 分钟后回收 |
| auto 存活时手动 start | 接管（无任务）或拒绝（有任务，提示原因） |
| auto 存活时用户 stop | 直接停（管理权） |
| 回收瞬间手动 start（竞态） | stale 探测兜底：PID 死了 → 正常启动 |
| manual 存活时 kl tui / kl run | 直接连接，不重复拉起 |
| auto 进程回收后用户再 kl tui | 再次自动拉起（幂等） |
| auto 回收时正好有状态写入 | 优雅退出 + 全状态已持久化，零损失 |

## 5. 实现要点

| 组件 | 改动 |
|---|---|
| `cli/src/commands/server.ts` | daemon.json 读写（pid/source/started_at）；start 分支接管逻辑；stale 探测；`KL_DAEMON_SOURCE` 环境变量传递；**自举逻辑**（~/.kl/venv 检测 → 创建 + 安装 → PATH 探测 → 报错） |
| `cli/src/tui/app.tsx` | 连接失败（网络错误）→ 自动拉起（复用 init 的 serverStart 逻辑）→ 轮询 /health → 重试 |
| `cli/src/api/events.ts` | **WS 断线自动重连**（指数退避 1s/2s/4s…封顶 30s，重连后恢复事件流）——防"TUI 假死 + 服务端误回收" |
| `cli/src/commands/run.ts` | 同 tui：连接失败自动拉起 |
| `server/kl_server/main.py` | 路径显式化：config/db/audit 改用 `~/.kl/` 全局路径（不再依赖 cwd）；lifespan 空闲监控任务：读取 KL_DAEMON_SOURCE；周期检查运行中任务数 + WS 连接数；空闲 N 分钟 → 优雅退出 |
| `server/kl_server/config/loader.py` | 单一全局配置源（`~/.kl/config.yaml`），移除项目目录配置读取 |
| `server/kl_server/api/` | WS 连接计数暴露（供监控判断） |

## 6. 实施步骤

| 步骤 | 内容 | 工作量 | 状态 |
|---|---|---|---|
| 1 | daemon.json 来源标记 + 环境变量传递 + stale 探测 | 小 | ✅ 已实施 |
| 2 | **配置与数据路径全局化**（main.py 显式 `~/.kl/` 路径 + loader 单一全局源，摆脱 cwd 依赖） | 中 | ✅ 已实施 |
| 3 | **全局自举 venv**（~/.kl/venv 检测/创建/安装 + 版本注入 + TTY/非 TTY 提示 + 无 python 报错） | 中 | ✅ 已实施 |
| 4 | 服务端空闲监控（lifespan 后台任务：任务/WS 计数 + 计时 → 优雅退出） | 中 | ✅ 已实施 |
| 5 | 手动 start 接管逻辑（auto → 停旧起新 / 有任务拒绝） | 中 | ✅ 已实施 |
| 6 | tui / run 自动拉起（复用 init 已修逻辑） | 小 | ✅ 已实施 |
| 7 | **WS 断线自动重连**（events.ts 指数退避，防假死 + 误回收） | 小 | ✅ 已实施 |
| 8 | 测试：auto 回收 / manual 不回收 / 任务保活 / WS 断开重连取消回收 / 接管 / stale / 幂等 / 全局配置迁移 / 自举各分支 | 中 | ✅ 已实施 |

**合计约 2 天。**

> 截至 2026-08-09：步骤 1/2/3/4/5/6/7/8 已完成。

## 7. 配套项

### 7.1 审批超时（promise_state P1-6） ✅ 已实现

挂起审批不阻塞回收的前提——超时自动拒绝 → 任务继续或结束 → 可安全回收。建议与本设计同步或先行实施。

**推荐配置**：

```yaml
# ~/.kl/config.yaml
guardrail:
  approval_timeout_seconds: 300     # 默认 5 分钟；范围建议 30 ~ 1800
```

> 已实现：`guardrail.approval_timeout_seconds` 默认 300s；超时返回 `timeout` 决策并自动拒绝该动作；`approval_complete` 审计记录 `decision=timeout`；TUI 审批面板显示倒计时，超时后提示“审批超时，已自动拒绝该动作”。

| 使用场景 | 建议值 |
|---|---|
| 默认（混合） | 300s |
| 重度无人值守（跑批任务链） | 60-120s |
| 重度交互（人在场、任务谨慎） | 600-1800s |

**语义**：超时 = **自动拒绝该动作**（不冻结任务）——拒绝后 agent 收到反馈（`decision: reject` 路径已存在）→ 换方案继续，无人值守也能推进。SPEC 允许"拒绝或冻结"，拒绝更符合"长期可用、后台执行"定位。

**配套体验**：
1. TUI 审批面板**倒计时**（"剩余 4:32"）——用户不猜会不会超时
2. **超时事件进审计**：`approval_complete` 已有 decision 字段，补 `decision="timeout"` 分支——用户回来可查"为什么动作被拒"
3. TUI 消息区提示"审批超时，已自动拒绝该动作"

**实现位置**：HITLManager 加超时字段 + approval 请求记录时间戳；agent_loop 的 `on_approval` 等待加 `asyncio.wait_for`（超时返回 "timeout" 决策）。约半天工作量。

### 7.2 kl init 自动拉起（已完成）

作为 auto 来源的第一实现，tui/run 复用同一逻辑（kl init 连接被拒 → 自动 server start → 轮询 /health → 重试，仅网络错误触发）。

## 8. 明确不做（本次范围外）

- 开机自启 / 系统服务注册（systemd/LaunchAgent/服务管理器）——后续可选
- 远程访问 / TLS——§12 未授权范围
- 任务级生命周期管理（暂停/恢复的进程语义）——保持现状
- 项目级配置 / 项目级初始化（配置纯全局，项目上下文 = TUI 工作目录）

## 9. 环境解耦：全局自举 venv（定稿）

**目标**：daemon 的运行环境不依赖"触发目录附近的 venv"——在哪启动都能拉起。**自举 = 找不到环境就造一个**（固定位置 ~/.kl/venv），而非在启动目录周边找现成 venv。

### 9.1 方案

```
拉起时检测顺序：
  1. ~/.kl/venv/bin/python 能导入 kl_server → 直接用（环境全局唯一，零探测）
  2. PATH 探测（python/python3/py 能导入 kl_server）→ 用
  3. 以上都无 → 自举：
       python -m venv ~/.kl/venv
       安装 kl-server：
         发布模式：~/.kl/venv/bin/pip install "kl-server==<SERVER_VERSION>"
         源码模式：~/.kl/venv/bin/pip install -e <源码 server 目录>
                   （自动发现：触发目录向上找 server/；找不到提示先 make install）
  4. 自举失败（无 python）→ 明确报错（见 9.3）
```

对**已 pip 安装的用户零影响**（第 2 步命中即跳过自举）；"只装 CLI"的用户获得自动装 server 的体验。

### 9.2 版本对齐

```
CLI 构建时（npm run build 前置步骤）：
  从 server/pyproject.toml 读 version → 生成 cli/src/server-version.ts 常量

自举时：pip install "kl-server==<SERVER_VERSION>"   ← 精确锁定，绝不漂移
  PyPI 无该精确版本 → 明确报错"server 包版本 X 未发布"

CI dist-check 增加一步：断言 cli 内置 SERVER_VERSION == pyproject version
```

理由：`>=` 范围会漂移；精确锁定 + 构建注入 + CI 校验让版本错配在构建期暴露，不留给用户运行时。发布流程要求两个包同版本发布。

### 9.3 无 python 降级

自举失败（PATH 中无 python/python3/py，无法创建 venv）时明确报错，**给三条可操作路径**：

```
"未找到可用的 Python（>= 3.11）。
 可选处理：
 a) 安装 Python 后重试
 b) 手动执行：pip install kl-server
 c) 用项目 venv 手动启动：<venv>/bin/python -m uvicorn kl_server.main:app ..."
```

### 9.4 首次知情提示

```
首次自举时：
  TTY（kl tui 交互终端）：
    "首次运行将创建全局环境 ~/.kl/venv 并安装 kl-server（版本 X），是否继续？[Y/n]"
 非 TTY（kl run 脚本/管道场景）：
    不阻塞，直接自举；输出说明"已自动创建全局环境 ~/.kl/venv（kl-server X）"
```

理由：交互场景用户知情；无人值守场景不阻塞且留痕可查。

### 9.5 对现有实现的替代 ✅ 已清理

定稿后 `discoverVenvCandidates`（触发目录向上找 venv）不再需要——环境来源固定为 ~/.kl/venv 或 PATH，已删除该探测逻辑和相关测试。
