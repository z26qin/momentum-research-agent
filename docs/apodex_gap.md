# 闭环进度：Momentum Factor Risk Research Agent

目标不是通用 Heavy-Duty Solver。目标是 **Apodex 形态的受控闭环**，但垂直只做 US equity **momentum factor risk**（Daniel–Moskowitz crash、crowding、unwind）。credit / macro / flow / technicals 只作为动量尾部的 overlay，不是独立产品线。

对照：[Apodex 1.1](https://arxiv.org/html/2608.23283) 受控闭环；[FrontierAgent](https://github.com/ApodexAI/FrontierAgent) 的 Agent Team（活 task board、staged return、独立 Statement Review）。本仓库绑冻结 DeepSeek API，不做权重 SFT/RL，也不做 AgentBus / SpawnGuard。闭环的系统级等价物：session 失败 → 缺口账本 → 新的动量研究任务 → 可验证引擎环境 → 再规划 → 轨迹 → 改 prompt/工具/任务模板。

## Status

```
目标  Apodex-style closed loop × momentum factor risk only
main  [████████░░░░░░░░░░░░]  38/100  verified_runtime   SHA 5e970ef
```

探针：17 / 22 信号（schema +1：`gap_seed`）。`python3 scripts/probe_apodex_gap.py origin/main`

| | 环节 | main 现在 | 还缺（垂直闭环） |
| ---: | --- | --- | --- |
| 1 | 编排骨架 | **有**：TaskBoard、分解/并行/综合、ReAct | — |
| 2 | 动量环境 | 读 monitor 快照；无快照则 labeled mock | 真 DM 引擎跑批 + 独立于进程退出的 \(V_D\) |
| 3 | 非对称验证 | 独立 Verifier + static audit + conservative merge | crowding/unwind **断言**级 statement review |
| 4 | 再规划 | 一轮 follow-up（最多 2 任务，只修 REJECTED/UNCHECKED） | 执行中途改共享计划、停支 |
| 5 | 缺口账本 | **有**：跨 session `gap_ledger.jsonl` OPEN/CONSUMED/CLOSED | 分类仍是关键词；`SOURCE_QUALITY` 不种植 |
| 6 | 任务工厂 | **有**：下轮最多 2 个 `kind=gap`；一轮 follow-up | 从缺口生成**新**动量研究场景，不是只修旧 claim |
| 7 | 轨迹学习 | `traces.jsonl` + `ToolTrace` 可回放 engine/search | 从轨迹进化 prompt/工具（且不进 verifier） |
| 8 | 评测回流 | 单测 + verifier + ledger replay tests | 动量研究交付基准，失败可重开进账本 |

```
✅ 已在 main（#2 + #5 + #6 + #7）
   磁盘 TaskBoard · decompose/dispatch/synthesize
   独立 Verifier（只判 evidence_id）· 一轮 follow-up
   engine 快照适配器 · LoopBudget
   verification.json gaps[] + traces[] · traces.jsonl · replay_trace
   reports/gap_ledger.jsonl · seed_open_gaps（最多 2）· verify 后 CLOSED/OPEN

⬜ 闭环还没做（不要用 #10 的现状充数）
   真引擎 + 独立 \(V_D\)（不是 subprocess 退出码）
   活的再规划（不是「再打一次 engine_query」）
   从轨迹进化 prompt（且 overlay 不进 verifier）
   评测驱动下一轮（多于一条冻结日，失败可重开）
```

机器可读：`apodex_gap.json`。

## 当前基线

| 字段 | 值 |
| --- | --- |
| 评审 SHA | `5e970ef` *Merge pull request #7 from z26qin/aaron/gap-resolve* |
| 评审时间 | 2026-09-04 |
| 综合分 | **38 / 100**（verified_runtime） |
| `main` 上的提交 | 含 #2 / #5 / #6 / #7 |
| 刚合入 | [PR #6](https://github.com/z26qin/momentum-research-agent/pull/6) + [PR #7](https://github.com/z26qin/momentum-research-agent/pull/7)。探针 17/22（+`gap_seed`）。正式分 30→38 |

## 分维

分数是相对 Apodex 该环节的完整度，不是相对「一个 CLI 研究 agent」的完成度。

| 维度 | 分 | 已有证据 | 仍缺 |
| --- | ---: | --- | --- |
| 能力缺口挖掘 | 40 | session `gaps[]` + 跨 session `gap_ledger.jsonl`（`MomentumCapability`，OPEN/CONSUMED/CLOSED） | 分类是关键词；`SOURCE_QUALITY` 不种植 |
| Task Pipeline | 22 | `followup_specs()` + `seed_open_gaps()` 最多 2 个 `kind=gap` | 修旧 claim，不是新研究世界工厂 |
| Environment Scaling | 22 | `engine_adapter` 读 monitor 快照；无快照则 mock | 无独立 \(V_D\)、不跑 PIT 管道 |
| Agentic Coordination Scaling | 32 | verify → 一轮 follow-up → re-verify | 无中途再规划、停支、异步介入 |
| 非对称验证 | 40 | 独立 `Verifier` + static audit + conservative merge | 无 statement-level counterexample |
| 轨迹学习 | 12 | `traces.jsonl` + `ToolTrace` + `replay_trace` | 无 prompt/工具自进化 |
| 评测归因 | 20 | 单测 + audit/verifier/followup/engine/ledger/gap replay | 失败不进可重开的评测回流 |

## 架构对照（相对论文，不是相对愿望）

当前运行路径：

```
CLI → Coordinator.run
        ├─ decompose()
        ├─ seed_from_ledger()   最多 2 个 kind=gap
        ├─ dispatch_all()
        ├─ verify()             独立 Verifier → verification.json
        ├─ resolve_consumed_gaps()  CLOSED 或回到 OPEN
        ├─ follow_up()          至多一轮，只修 rejected/unchecked
        ├─ verify()
        └─ synthesize()
```

Apodex 1.1 Agent Team 要把分解写进**活的** task board，并在执行中：阶段性回传、改共享计划、停掉过时分支、接受 \(u_t\) 介入、用更窄的 verifier 打关键断言。

本仓库已经对齐的外形：

- 磁盘 `task_board.json`（`TaskBoard` 每次 mutation 都 `save()`）
- lead / sub-agent 分裂
- 子代理失败不拖垮 coordinator（`return_exceptions=True`）
- 跨 session 缺口账本会被下一轮消费（#6+#7）

这是闭环的**账本段**，不是环境段或协调段。

刻意相反的设计：`decompose.md` 仍要求任务 *self-contained, without seeing other tasks' results*。Apodex 的协调缩放依赖「一个分支的结果改写共享计划」。要靠近自我改进，这块必须改，而不是再加固定 profile。

## 最近能真正动针的下一刀

#6+#7 已完成后，不要做「把 monitor 整树 vendor 进本仓库」。

1. Engine 保持 **subprocess + 上游 pin**（`MOMENTUM_ENGINE_DIR` / sibling）。本仓库最多留 manifest + 小 JSON 金样。
2. \(V_D\) 独立于 subprocess 退出：重算 `risk_state` / fingerprint / as_of；crowding/unwind **断言**由 verifier 打。
3. Replan 只在 BLOCKED 或真 mock / `verdict=fail`。作业应改共享计划，不是再打一次同一工具。`engine_query` 无 `end` 不能静默跳过 pipeline 再触发 replan。
4. Overlay 只给研究 profile；`Verifier` 不吃 `profile_hints.md`。
5. `--eval` 至少两条冻结日（含非 `normal`），同一 `evidence_id` 可重开。

[#10](https://github.com/z26qin/momentum-research-agent/pull/10) 预估 48，**不得**在合入前记到 main。阻断：浅 \(V_D\)、过宽 replan、overlay 进 verifier、49MB engine vendor、同步 90s warm。详见该 PR 评论。

`AGENTS.md` 明确不做：LangChain/LangGraph/CrewAI、Web UI、Docker、数据库、MCP、AgentBus、无界 follow-up、对 DeepSeek 权重做 SFT/RL。

## PR #7 已合入

https://github.com/z26qin/momentum-research-agent/pull/7 于 2026-09-04 合入 `main`（`5e970ef`）。`CONSUMED` 表示种了 `kind=gap`；verify 后同一 jsonl 行变为 `CLOSED` 或回到 `OPEN`。正式分 30→38。

## PR #6 已合入

https://github.com/z26qin/momentum-research-agent/pull/6 于 2026-09-04 合入 `main`（`d533120`）。`seed_open_gaps()` 下轮最多 2 个 `kind=gap`。单独看还不能把分打到 38，因为 CONSUMED 行当时不会闭环；#7 补上。

## PR #5 已合入

https://github.com/z26qin/momentum-research-agent/pull/5 于 2026-09-04 合入 `main`（`abd007b`；#4 为同一切片）。session ledger + traces。正式分 22→30。

## PR #2 已合入

https://github.com/z26qin/momentum-research-agent/pull/2 于 2026-09-04 合入 `main`（`5212820`）。正式分 8→22。

## 更新规则

1. `git fetch origin main`，对 `last_reviewed_sha..origin/main` 做 diff。
2. 跑 `python3 scripts/probe_apodex_gap.py origin/main`（脚本用 `git grep` 扫指定 ref，不必 checkout 到 main）。
3. 只给**被 diff 实际推进的维度**改分；probe 命中只是证据，不是分数。没有新提交则不改正式分。
4. 同步改 `apodex_gap.json` 的 `last_reviewed_sha`、`last_reviewed_at`、`last_probe` 和对应 `dimensions[].score_0_to_100`。
5. 在下面追加一行历史，不要改写旧行。
6. `live_replan` 必须是 `replan_blocked` / `staged_return` / `class AgentBus` 一类符号。`should_replan` / `maybe_replan` **不算**。

## Probe 快照（2026-09-04 18:40 UTC）

可复跑：`python3 scripts/probe_apodex_gap.py origin/main`

| 维度 | main 命中 | 仍缺 |
| --- | --- | --- |
| 缺口挖掘 | Task + BLOCKED + EvidenceVerdict + capability_ledger | — |
| Task Pipeline | followup_specs, TaskKind.FOLLOWUP, **gap_seed** | 新环境工厂 |
| 环境缩放 | engine_adapter + mock 回退 | delivery_verifier / \(V_D\) |
| 协调缩放 | TaskBoard + `follow_up()` | live replan / staged return |
| 非对称验证 | Verifier + static_audit + conservative merge | 深度仍远小于 Statement Review |
| 轨迹学习 | trajectory_log (`ToolTrace` / `replay_trace`) | prompt 进化 |
| 评测归因 | 单测 + verifier tests | working-capability 基准 |

探针 schema 从 21 增到 22（+`gap_seed`）。旧 16/21 对应新 17/22。`live_replan` 仍不把「AgentBus out of scope」或 `maybe_replan` 算命中。

PR #10（未合入，head `e490aa5`）探针 19/22（+`delivery_verifier` + `prompt_evolution`），预估综合分 48，**不得**在合入前记到 main。

## 历史

| 日期 | SHA | 综合分 | 笔记 |
| --- | ---: | ---: | --- |
| 2026-09-04 | `ef03fa5` | 8 | `main` 唯一提交：Phase 1 骨架。闭环六段均未作为代码存在。 |
| 2026-09-04 | `ef03fa5`（main 未变） | 8 | 预评草稿 PR #2：合入后综合分约 22。正式分不改，直到该 diff 进入 `main`。 |
| 2026-09-04 | `ef03fa5`（main 未变） | 8 | 增加 `scripts/probe_apodex_gap.py`。main 命中 5/21 信号；PR #2 命中 14/21。轨迹学习两边都是 0。 |
| 2026-09-04 | `ef03fa5`（main 未变） | 8 | 探针加回归测试与 main/PR CI。`live_replan` 不再把「AgentBus out of scope」算命中。 |
| 2026-09-04 | `ef03fa5`（main 未变） | 8 | 复核 PR #2 `5212820`：有 `verify`/`follow_up` 和 `verification.json`；无 Statement Review、无可回放轨迹。预估 22 维持。 |
| 2026-09-04 | `ef03fa5` | 8 | 目标收窄为垂直闭环（momentum factor risk only）。文档顶部改为 status bar：main 8 / PR#2 预估 22。 |
| 2026-09-04 | `5212820` | 22 | PR #2 合入。探针 14/21。正式分 8→22。轨迹学习仍 0。 |
| 2026-09-04 | `abd007b` | 30 | PR #5 合入。session ledger + traces。探针 16/21。正式分 22→30。跨 session 消费仍缺。 |
| 2026-09-04 | `5e970ef` | 38 | PR #6+#7 合入。跨 session gap seed + CLOSED/OPEN。探针 17/22（+`gap_seed`）。正式分 30→38。#10 预估 48，不合入。 |
