# 计划文档索引

本目录集中描述 KL Code 的规划文档存放位置，便于后续 implementer / reviewer 快速定位“主计划”与“执行进度”。

## 主计划

- 总计划：仓库根目录 [`/PLAN.md`](../../../PLAN.md)，按 Phase 和 Task 划分全部实现步骤。
- 规则文档：根目录 `SPEC_PROCESS.md` 描述工作流约定（worktree、评审、提交）；`SPEC.md` 为产品规范。

## 执行进度

- 控制器台账：`.superpowers/sdd/PLAN/progress.md`（位于主工作区，**本地专用、被 git 忽略**，不进入版本库）。它记录 Phase 进度与各任务状态。
- 任务日志：根目录 `AGENT_LOG.md`，按日期与 task 编号追加“技能、验证、文件、教训”等执行记录，随 PR 进入版本库。
- 单个任务的 brief/report 历史存放在 `.superpowers/sdd/PLAN/`（本地），同样 git-ignored。

## 分阶段文档组织

- 每个任务使用独立 worktree（`.claude/worktrees/task-*`）与对应分支完成，最终并入待推送链。
- 版本库内长期保留的规划和文档为根目录的 `PLAN.md`、`SPEC.md`、`SPEC_PROCESS.md`、`AGENT_LOG.md`，以及 `docs/` 下的说明性文档。
- 本文件所在层级不承载 Phase 内容；Phase 细节在根 `PLAN.md` 与本地台账/任务日志中维护。
