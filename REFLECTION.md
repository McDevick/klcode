# REFLECTION：Superpowers 与 subagent 流程复盘

## 1. 最有用的技能

最有用的是 `test-driven-development` 和 `subagent-driven-development`。前者把“完成”从自我判断变成可执行红绿证据：5.1 的 `ModuleNotFoundError`、5.3 的构建/打包失败都直接暴露缺口；后者让每个 task 有独立 worktree、独立 diff 和独立验证，出错时能快速定位是哪一步偏离。

`using-git-worktrees` 在跨 task 协作中同样关键。Phase 4 的 P-1 证明，一旦把 4.1-4.11 塞进单一 `worktree-phase-4`，规则会失守；Phase 5 改为 stacked worktree 后，AGENT_LOG 作为共享文件也能保持每 task 可审。

## 2. 形式大于实质的部分

`requesting-code-review` 的两阶段评审在代码任务中有效，但文档/构建任务里如果只走模板，容易变成形式。真正纠错的是执行命令：Task 5.3 跑 `npm pack --dry-run` 才发现 tarball 没有 bin 产物，跑 server build 才发现缺 `build` 前端；Task 5.2 的 `--pyargs` 不一致也是评审与 Makefile 对照后修复，而不是模板本身保证质量。结论：评审要绑定验证命令，否则只是再读一遍。

## 3. TDD 是阻碍还是放大器

是放大器。AI 容易自信地说“已经完成”，TDD 给出不可抵赖的锚点。对机制代码，红到绿很自然；对文档/分发，verification-first 更合适：先让命令失败，再修到通过。Task 5.3 的基线失败比先写配置再“感觉成功”更能暴露真实状态。

## 4. 自主运行时长与漂移

单 task 内约 1-2 小时可保持稳定；跨 task 连续 2-4 小时后，漂移概率明显上升。Phase 4 是一次反例：会话切换后丢失 worktree 规则，把一个 phase 当成一个 task。只要 prompt 只给当前 task、文件清单和验证命令，fresh subagent 可以在一个 task 内自主；但“继续做下一件事”不能交给同一上下文太久。

## 5. 最优 task 粒度

1-2 小时、一个文件集、一个可验证结果最优。5.1 是 4 个 demo 加 1 个测试文件，5.3 是分发元数据加构建验证，都能一次审完。Phase 4 一次 11 个 task 过粗，问题定位和评审都困难。

## 6. SPEC/PLAN 质量与偏离案例

SPEC/PLAN 越明确，subagent 越少自由发挥。最接近的偏离案例是 Task 4.7：PLAN 给出 `.kl/tools/<name>/` 目录契约，首版插件 loader 却实现成扁平文件，直到 quality review 才修正为 `<name>/tool.py`。另一例是 Task 5.2 初版 README 写了 `pytest --pyargs`，与 Makefile 不一致，靠修复提交 `5703874` 对齐。Task 5.6 一直 pending 也说明 PLAN 曾缺少 bootstrap 任务：模块各自可测，不等于应用能被组装起来。SPEC 承诺、PLAN 任务、验证命令三者必须双向核对。

## 7. 最有效的 prompt/context 策略

“当前 task 只改哪些文件、跑哪些验证、明确不做哪些事”最有效。5.3 能在范围内不注册 `tui`、不虚构 license，正是因为 prompt 把边界写清楚。fresh subagent 不需要完整历史，需要的是精确契约和可执行验收。

## 8. 凭据与分发迫使想清的问题

凭据要求让我不再默认“本地能跑就算完成”，而是想 keyring/加密文件/.env、token 文件权限、日志脱敏、CLI 不回显。分发要求让我处理依赖下限、console entry、esbuild bundle、`files=["dist"]`、包内 README 和生成产物忽略。Task 5.3 还发现 server main 导入会创建 token，导致 CLI 事件测试对默认 token 路径敏感；这类副作用只在真实构建验证中暴露。

## 9. 重做会改变什么

更早做 SPEC 到 PLAN 双向矩阵；每个 task 模板强制包含“不做清单”；Phase 4 不合并多个 task；文档类任务直接用命令核验而不是只评审文字。

## 10. 对 Superpowers 的批判

它假设 task 可独立拆、subagent 能保持上下文、TDD 红绿足以防漂移、worktree/PR 会自动形成干净历史。本项目里这些假设部分成立：5.1-5.3 的小 task 流程稳定，但 Phase 4 证明单一会话不能承担多 task；共享 AGENT_LOG 也迫使 Phase 5 从并行 worktree 改成 stacked。方法论真正有用的是强制检查清单，但控制器仍必须持续审计 scope 和验证证据，不能假设技能自动保证不偏。
