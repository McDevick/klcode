# REFLECTION：Superpowers 与 subagent 流程复盘

## 1. 最有用的技能

最有用的是 `test-driven-development` 和 `subagent-driven-development`。前者把“完成”从自我判断变成可执行红绿证据：5.1 的 `ModuleNotFoundError`、5.3 的构建/打包失败都直接暴露缺口；后者按每 task 派独立 implementer（ID 记录于 AGENT_LOG 对应条目），并有独立 worktree、独立 diff 和独立验证，出错时能快速定位是哪一步偏离。

`using-git-worktrees` 在跨 task 协作中同样关键。Phase 4 的 P-1 证明，一旦把 4.1-4.11 塞进单一 `worktree-phase-4`，规则会失守；Phase 5 改为 stacked worktree 后，AGENT_LOG 作为共享文件也能保持每 task 可审。

## 2. 形式大于实质的部分

`requesting-code-review` 的两阶段评审在代码任务中有效，但文档/构建任务里如果只走模板，容易变成形式。真正纠错的是执行命令：Task 5.3 跑 `npm pack --dry-run` 才发现 tarball 没有 bin 产物，跑 server build 才发现缺 `build` 前端；Task 5.2 的 `--pyargs` 不一致也是评审与 Makefile 对照后修复，而不是模板本身保证质量。结论：评审要绑定验证命令，否则只是再读一遍。

## 3. TDD 是阻碍还是放大器

是放大器。AI 容易自信地说“已经完成”，TDD 给出不可抵赖的锚点。对机制代码，红到绿很自然；对文档/分发，verification-first 更合适：先让命令失败，再修到通过。Task 5.3 的基线失败比先写配置再“感觉成功”更能暴露真实状态。

## 4. 自主运行时长与漂移

单 task 内约 1-2 小时可保持稳定；跨 task 连续 2-4 小时后，漂移概率明显上升。Phase 4 是一次反例：会话切换后丢失 worktree 规则，把一个 phase 当成一个 task。只要 prompt 只给当前 task、文件清单和验证命令，独立 implementer subagent 可以在一个 task 内自主；但“继续做下一件事”不能交给同一上下文太久。

## 5. 最优 task 粒度

1-2 小时、一个文件集、一个可验证结果最优。5.1 是 4 个 demo 加 1 个测试文件，5.3 是分发元数据加构建验证，都能一次审完。Phase 4 一次 11 个 task 过粗，问题定位和评审都困难。

## 6. SPEC/PLAN 质量与偏离案例

SPEC/PLAN 越明确，subagent 越少自由发挥。最接近的偏离案例是 Task 4.7：PLAN 给出 `.kl/tools/<name>/` 目录契约，首版插件 loader 却实现成扁平文件，直到 quality review 才修正为 `<name>/tool.py`。另一例是 Task 5.2 初版 README 写了 `pytest --pyargs`，与 Makefile 不一致，靠修复提交 `5703874` 对齐。Task 5.6 一直 pending 也说明 PLAN 曾缺少 bootstrap 任务：模块各自可测，不等于应用能被组装起来。SPEC 承诺、PLAN 任务、验证命令三者必须双向核对。

## 7. 最有效的 prompt/context 策略

“当前 task 只改哪些文件、跑哪些验证、明确不做哪些事”最有效。5.3 能在范围内不注册 `tui`、不虚构 license，正是因为 prompt 把边界写清楚。独立 implementer subagent 不需要完整历史，需要的是精确契约和可执行验收。

## 8. 凭据与分发迫使想清的问题

凭据要求让我不再默认“本地能跑就算完成”，而是想 keyring/加密文件/.env、token 文件权限、日志脱敏、CLI 不回显。分发要求让我处理依赖下限、console entry、esbuild bundle、`files=["dist"]`、包内 README 和生成产物忽略。Task 5.3 还发现 server main 导入会创建 token，导致 CLI 事件测试对默认 token 路径敏感；这类副作用只在真实构建验证中暴露。

## 9. 重做会改变什么

更早做 SPEC 到 PLAN 双向矩阵；每个 task 模板强制包含“不做清单”；Phase 4 不合并多个 task；文档类任务直接用命令核验而不是只评审文字。

## 10. 对 Superpowers 的批判

它假设 task 可独立拆、subagent 能保持上下文、TDD 红绿足以防漂移、worktree/PR 会自动形成干净历史。本项目里这些假设部分成立：5.1-5.3 的小 task 流程稳定，但 Phase 4 证明单一会话不能承担多 task；共享 AGENT_LOG 也迫使 Phase 5 从并行 worktree 改成 stacked。方法论真正有用的是强制检查清单，但控制器仍必须持续审计 scope 和验证证据，不能假设技能自动保证不偏。

## 11. daemon 生命周期是“启动方式决定归属”的实践

server-redesign 的核心原则值得单独记录：**生命周期归属 = 启动方式**。用户手动 `kl server start` 得到 manual 来源，用户自己管理；TUI/run/init 自动拉起得到 auto 来源，空闲时自动回收。这个设计把“用户资产”和“借来的服务”分开，比单纯加一个“后台进程”更接近真实使用场景。

这次实现里最容易出错的不是启动本身，而是三类边缘状态：

1. stale PID：进程死了但 pid 文件还在，旧实现会误报 already running，服务永远起不来。修复方式是启动前先探测进程存活，死了就清理并正常启动。
2. 来源接管：auto daemon 存活时用户手动 start，不能简单报 already running；应该区分“无任务可接管”和“有任务必须拒绝”。有任务时直接杀掉会让用户丢失后台执行承诺。
3. 空闲回收：auto 来源必须同时检查运行任务和 WS 连接。任务没结束不能回收，TUI 开着即使不操作也不能回收；否则会出现“用户回来发现 agent 死了”的假死体验。

这提醒我：生命周期代码表面是 PID 和进程管理，实际是用户心智模型的管理。manual/auto、运行中/空闲、有任务/无任务这些状态必须显式建模，不能靠临时判断拼出来。

## 12. 自动拉起最容易踩的是“环境漂移”

自动拉起让我重新理解“能导入 kl_server”并不等于“用的是当前代码”。这次实际遇到一个非常典型的坑：PATH 里的系统 Python 能导入一个旧 worktree 的 `kl_server`，于是自动服务端跑的是旧代码，mock 模型表现异常；手动服务端走项目 venv，反而正常。

修复后我总结出三条环境规则：

1. 优先使用全局 `~/.kl/venv`，它应该是唯一可控的全局环境。
2. PATH 探测在源码仓库场景下必须校验 `kl_server.__file__` 是否在当前 `server/` 内，否则旧 worktree/系统包会被误判为可用。
3. 自举前要清理损坏的全局 venv。MSYS Python 创建的 venv 布局是 `bin/python.exe`，Windows 常见的 `Scripts/python.exe` 探测会漏掉，导致自举“看起来成功”但实际没有可用的 server。

另外，自动 daemon 之前没有日志，排障只能靠猜。现在 `~/.kl/daemon.log` 会捕获 uvicorn 输出。以后遇到“自动拉起能用但行为不对”，第一件事应该是看 daemon.log 和 `daemon.json`，而不是反复重启。

## 13. 全局化不是“把路径改成 home 就结束”

server-redesign 把配置、数据库、审计、记忆全部移到 `~/.kl`，同时把 skill 和用户工具也改成全局：

- `~/.kl/config.yaml`：provider/key/模型/MCP/沙箱/审批超时
- `~/.kl/kl.db`、`~/.kl/memory.db`：会话、任务、记忆、指令沉淀
- `~/.kl/audit.jsonl`：审计日志
- `~/.kl/skills/`：全局 skill
- `~/.kl/tools/`：全局用户工具
- `~/.kl/user-rules.md`：全局用户规则

项目目录里仍然保留项目级内容：`.kl/rules.md`、`AGENTS.md`、`tool_outputs/`。服务端启动时不再在启动目录创建 `.kl/skills/` 或 `.kl/tools/`，避免“在任意目录打开 TUI 就污染目录”的副作用；`tool_outputs` 改为需要时才在 session 工作区创建。

这个过程的教训是：全局化不能只移动配置文件，还要考虑“启动有没有副作用”“旧数据怎么办”“哪些内容按项目走”。否则会出现配置是全局的，但 skill 还跟着 daemon cwd 这种不一致。

## 14. 会话用户规则退出规则栈，全局用户规则接管

之前规则栈是“用户指令沉淀 > 用户规则 > 项目规则 > 默认”，但用户规则实际存在 session 的 `rules` 字段里，跨 session 不可见，也缺少一个自然的书写位置。现在改成：

```text
用户指令沉淀 > 全局用户规则 > 项目规则 > 默认行为
```

全局用户规则独立为 `~/.kl/user-rules.md`，项目规则仍是 `<项目>/.kl/rules.md` 或 `AGENTS.md`。session.rules 虽然保留兼容字段，但不再注入上下文。这个改动很小，却让“用户的话”有了稳定载体，也让“项目差异”只通过 session.workspace 的项目规则表达。

## 15. 上下文压缩的“记得什么”必须可验证

上下文重构 Phase 1-3 完成后，模型并不是“压缩后还记得旧历史”，而是记得结构化摘要和少量原始窗口。具体机制：

- A 桶对话/决策：旧对话交给 LLM 摘要，保留最近 4 条原始。
- B 桶工具结果：保留最近 2 条完整结果，更早的引用 `.kl/tool_outputs/<file>`。
- C 桶反馈：按类别去重，只保留最新一条。

压缩后模型还能看到 rules、task_plan、continuation_context、memory 配额和用户指令沉淀，但旧工具输出如果没有落盘引用就会丢失。这让我意识到：**上下文压缩不是“无损压缩”，而是“有损摘要 + 可追溯引用”**。如果希望模型继续，关键路径、命令、失败信息必须进摘要或落盘引用，否则恢复不了。


总体而言，这轮迭代的价值不只是功能变多，而是把“本地可跑”推进到“可部署、可发布、可排障”。下一步应该围绕真实安装、真实长任务、真实发布产物做验收。
