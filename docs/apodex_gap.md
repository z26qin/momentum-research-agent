# 闭环进度：Momentum Factor Risk Research Agent

目标不是通用 Heavy-Duty Solver。目标是 **Apodex 形态的受控闭环**，但垂直只做 US equity **momentum factor risk**（Daniel–Moskowitz crash、crowding、unwind）。credit / macro / flow / technicals 只作为动量尾部的 overlay，不是独立产品线。

本仓库绑冻结 DeepSeek API，不做权重 SFT/RL。闭环的系统级等价物：session 失败 → 缺口账本 → 新的动量研究任务 → 可验证引擎环境 → 再规划 → 轨迹 → 改 prompt/工具/任务模板。

## Status

```
目标  Apodex-style closed loop × momentum factor risk only
main  [██████░░░░░░░░░░░░░░]  30/100  verified_runtime   SHA abd007b
```

探针：16 / 21 信号。`python3 scripts/probe_apodex_gap.py origin/main`

| | 环节 | main 现在 | 还缺（垂直闭环） |
| ---: | --- | --- | --- |
| 1 | 编排骨架 | **有**：TaskBoard、分解/并行/综合、ReAct | — |
| 2 | 动量环境 | 读 monitor 快照；无快照则 labeled mock | 真 DM 引擎跑批 + 交付合约 \(V_D\) |
| 3 | 非对称验证 | 独立 Verifier + static audit + conservative merge | crowding/unwind **断言**级 statement review |
| 4 | 再规划 | 一轮 follow-up（最多 2 任务，只修 REJECTED/UNCHECKED） | 执行中途改共享计划、停支 |
| 5 | 缺口账本 | **session** `verification.json` `gaps[]`；仍无跨 session 分类消费 | 跨 session 动量能力账本 → 下轮 GAP 任务 |
| 6 | 任务工厂 | follow-up 从验证失败长修补任务 | 从缺口生成下一批动量研究场景 |
| 7 | 轨迹学习 | `traces.jsonl` + `ToolTrace` 可回放 engine/search | 从轨迹进化 prompt/工具 |
| 8 | 评测回流 | 单测 + verifier + ledger replay tests | 动量研究交付基准，失败进跨 session 账本 |

```
✅ 已在 main（含刚合入的 PR #5）
   磁盘 TaskBoard · decompose/dispatch/synthesize
   独立 Verifier（只判 evidence_id）· 一轮 follow-up
   engine 快照适配器 · LoopBudget
   verification.json gaps[] + traces[] · traces.jsonl · replay_trace

⬜ 闭环还没做
   跨 session 缺口账本 · 动量任务工厂 · 真引擎 + V_D
   活的再规划 · 从轨迹进化 prompt · 评测驱动下一轮
```

机器可读：`apodex_gap.json`。

## 当前基线

| 字段 | 值 |
| --- | --- |
| 评审 SHA | `abd007b` *Merge pull request #5 from z26qin/aaron/momentum-gap-ledger* |
| 评审时间 | 2026-09-04 |
| 综合分 | **30 / 100**（verified_runtime） |
| `main` 上的提交数 | 6 |
| 刚合入 | [PR #5](https://github.com/z26qin/momentum-research-agent/pull/5)（#4 为重复切片）。探针 16/21。正式分 22→30 |

## 分维

分数是相对 Apodex 该环节的完整度，不是相对「一个 CLI 研究 agent」的完成度。

| 维度 | 分 | 已有证据 | 仍缺 |
| --- | ---: | --- | --- |
| 能力缺口挖掘 | 28 | session `gaps[]`（`GapKind` + `trace_ids`，`327738c` / `agents/ledger.py`） | 无跨 session jsonl，无 crowding/unwind 能力分类 |
| Task Pipeline | 8 | `followup_specs()` 从验证失败生成最多 2 个修补任务 | 下一轮不消费账本；不是新研究场景工厂 |
| Environment Scaling | 22 | `engine_adapter` 读 monitor 快照；无快照则 mock | 无 \(V_D\)、不跑 PIT 管道 |
| Agentic Coordination Scaling | 32 | verify → 一轮 follow-up → re-verify | 无中途再规划、停支、异步介入 |
| 非对称验证 | 40 | 独立 `Verifier` + static audit + conservative merge | 无 statement-level counterexample |
| 轨迹学习 | 12 | `traces.jsonl` + `ToolTrace` + `replay_trace` | 无 prompt/工具自进化 |
| 评测归因 | 20 | 单测 + audit/verifier/followup/engine/ledger replay | 失败不进跨 session 账本 |

## 架构对照（相对论文，不是相对愿望）

当前运行路径：

```
CLI → Coordinator.run
        ├─ decompose()
        ├─ dispatch_all()
        ├─ verify()          独立 Verifier → verification.json gaps[]/traces[]
        ├─ follow_up()       至多一轮，只修 rejected/unchecked
        ├─ verify()          再核一次
        └─ synthesize()
```

Apodex 1.1 Agent Team 要把分解写进**活的** task board，并在执行中：阶段性回传、改共享计划、停掉过时分支、接受 \(u_t\) 介入、用更窄的 verifier 打关键断言。

本仓库已经对齐的外形：

- 磁盘 `task_board.json`（`TaskBoard` 每次 mutation 都 `save()`）
- lead / sub-agent 分裂
- 子代理失败不拖垮 coordinator（`return_exceptions=True`）

这是闭环的**前提**，不是闭环。

刻意相反的设计：`decompose.md` 要求任务 *self-contained, without seeing other tasks' results*。Apodex 的协调缩放依赖「一个分支的结果改写共享计划」。要靠近自我改进，这块必须改，而不是再加固定 profile。

## 最近能真正动针的下一刀

1. 把 `verification.json` 的 gaps 收到跨 session 的 `reports/gap_ledger.jsonl`，下轮最多种 2 个 `kind=gap` 任务。
2. 给 `engine_query` 加交付合约 \(V_D\)，快照 stale 时跑 `scripts/run_monitor.py`。
3. BLOCKED 或 mock/stale/`V_D` fail 后最多 1 个 `kind=replan`（不是第二轮 follow-up）。
4. 从账本 + traces 生成 `profile_hints.md` overlay（不是改权重）。
5. 冻结 DM/crowding/unwind eval，失败写回账本。

1 不做，闭环在 session 边界仍然断开。5 已有原料（`traces.jsonl`），缺的是消费。

`AGENTS.md` 明确不做：LangChain/LangGraph/CrewAI、Web UI、Docker、数据库、MCP、AgentBus、无界 follow-up、对 DeepSeek 权重做 SFT/RL。

## PR #5 已合入

https://github.com/z26qin/momentum-research-agent/pull/5 于 2026-09-04 合入 `main`（`abd007b`；#4 为同一切片）。`327738c` 增加 `agents/ledger.py`、`ToolTrace`、`traces.jsonl`、`replay_trace`。正式分 22→30。探针 16/21（`capability_ledger` + `trajectory_log`）。下一轮 `Coordinator.run` 仍不读这些 gaps。

## PR #2 已合入

https://github.com/z26qin/momentum-research-agent/pull/2 于 2026-09-04 合入 `main`（`5212820`）。预估 22 成为正式分。探针 14/21。轨迹学习仍为 0。

## 更新规则

1. `git fetch origin main`，对 `last_reviewed_sha..origin/main` 做 diff。
2. 跑 `python3 scripts/probe_apodex_gap.py origin/main`（脚本用 `git grep` 扫指定 ref，不必 checkout 到 main）。
3. 只给**被 diff 实际推进的维度**改分；probe 命中只是证据，不是分数。没有新提交则不改正式分。
4. 同步改 `apodex_gap.json` 的 `last_reviewed_sha`、`last_reviewed_at`、`last_probe` 和对应 `dimensions[].score_0_to_100`。
5. 在下面追加一行历史，不要改写旧行。

## Probe 快照（2026-09-04 16:00 UTC）

可复跑：`python3 scripts/probe_apodex_gap.py origin/main`

| 维度 | main 命中 | 仍缺 |
| --- | --- | --- |
| 缺口挖掘 | Task + BLOCKED + EvidenceVerdict + capability_ledger | — |
| Task Pipeline | followup_specs, TaskKind.FOLLOWUP | 新环境工厂 |
| 环境缩放 | engine_adapter + mock 回退 | delivery_verifier / \(V_D\) |
| 协调缩放 | TaskBoard + `follow_up()` | live replan / AgentBus |
| 非对称验证 | Verifier + static_audit + conservative merge | 深度仍远小于 Statement Review |
| 轨迹学习 | trajectory_log (`ToolTrace` / `replay_trace`) | prompt 进化 |
| 评测归因 | 单测 + verifier tests | working-capability 基准 |

`live_replan` 匹配 `class AgentBus` / `async def replan` / `async def replan_blocked` / `def replan_specs` / `def staged_return`。文档里写「AgentBus is out of scope」不算命中。

PR #3（未合入，head `20a6be9`）探针 19/21，多了 `delivery_verifier`、`live_replan`、`prompt_evolution`。预估综合分约 50，**不得**在合入前记到 main。

## 历史

| 日期 | SHA | 综合分 | 笔记 |
| --- | --- | ---: | --- |
| 2026-09-04 | `ef03fa5` | 8 | `main` 唯一提交：Phase 1 骨架。闭环六段均未作为代码存在。 |
| 2026-09-04 | `ef03fa5`（main 未变） | 8 | 预评草稿 PR #2：合入后综合分约 22。正式分不改，直到该 diff 进入 `main`。 |
| 2026-09-04 | `ef03fa5`（main 未变） | 8 | 增加 `scripts/probe_apodex_gap.py`。main 命中 5/21 信号；PR #2 命中 14/21。轨迹学习两边都是 0。 |
| 2026-09-04 | `ef03fa5`（main 未变） | 8 | 探针加回归测试与 main/PR CI。`live_replan` 不再把「AgentBus out of scope」算命中。 |
| 2026-09-04 | `ef03fa5`（main 未变） | 8 | 复核 PR #2 `5212820`：有 `verify`/`follow_up` 和 `verification.json`；无 Statement Review、无可回放轨迹。预估 22 维持。 |
| 2026-09-04 | `ef03fa5` | 8 | 目标收窄为垂直闭环（momentum factor risk only）。文档顶部改为 status bar：main 8 / PR#2 预估 22。 |
| 2026-09-04 | `5212820` | 22 | PR #2 合入。探针 14/21。正式分 8→22。轨迹学习仍 0。 |
| 2026-09-04 | `abd007b` | 30 | PR #5 合入。session ledger + traces。探针 16/21。正式分 22→30。跨 session 消费仍缺。 |
