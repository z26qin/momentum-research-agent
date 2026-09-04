# 闭环进度：Momentum Factor Risk Research Agent

目标不是通用 Heavy-Duty Solver。目标是 **Apodex 形态的受控闭环**，但垂直只做 US equity **momentum factor risk**（Daniel–Moskowitz crash、crowding、unwind）。credit / macro / flow / technicals 只作为动量尾部的 overlay，不是独立产品线。

对照：[Apodex 1.1](https://arxiv.org/html/2608.23283) 受控闭环；[FrontierAgent](https://github.com/ApodexAI/FrontierAgent) 的 Agent Team（活 task board、staged return、独立 Statement Review）。本仓库绑冻结 DeepSeek API，不做权重 SFT/RL，也不做 AgentBus / SpawnGuard。闭环的系统级等价物：session 失败 → 缺口账本 → 新的动量研究任务 → 可验证引擎环境 → 再规划 → 轨迹 → 改 prompt/工具/任务模板。

## Status

```
目标  Apodex-style closed loop × momentum factor risk only
main  [██████████░░░░░░░░░░]  48/100  verified_runtime   SHA 7f3c893
```

探针：19 / 22 信号（`delivery_verifier` + `prompt_evolution` 亮；`live_replan` 仍不亮）。`python3 scripts/probe_apodex_gap.py origin/main`

| | 环节 | main 现在 | 还缺（垂直闭环） |
| ---: | --- | --- | --- |
| 1 | 编排骨架 | **有**：TaskBoard、分解/并行/综合、ReAct | — |
| 2 | 动量环境 | **有**：subprocess `run_mvp`；无 `end` 则 file snapshot / local_dm / mock | 独立于进程退出的 \(V_D\)；不要 49MB vendor 树 |
| 3 | 非对称验证 | 独立 Verifier + static audit + conservative merge | crowding/unwind **断言**；overlay **不得**进 verifier |
| 4 | 再规划 | 第一波后至多一个 `kind=replan` | 执行中途改共享计划、停支；触发过宽 |
| 5 | 缺口账本 | **有**：跨 session `gap_ledger.jsonl` OPEN/CONSUMED/CLOSED | 分类仍是关键词；`SOURCE_QUALITY` 不种植 |
| 6 | 任务工厂 | **有**：最多 2 个 `kind=gap`；一轮 follow-up；一个 `kind=replan` | 从缺口生成**新**动量研究场景，不是再打一次 `engine_query` |
| 7 | 轨迹学习 | `traces.jsonl` + `refresh_profile_hints` 运行时 overlay | 从轨迹进化 prompt/工具（且不进 verifier） |
| 8 | 评测回流 | `--eval` 一条冻结日，失败写 `eval:{case_id}` | 至少两条冻结日（含非 `normal`），失败可重开 |

```
✅ 已在 main（#2 + #5 + #6 + #7 + #9 + #10）
   磁盘 TaskBoard · decompose/dispatch/synthesize
   独立 Verifier（只判 evidence_id）· 一轮 follow-up
   live run_mvp via subprocess · LoopBudget
   verification.json gaps[] + traces[] · traces.jsonl · replay_trace
   reports/gap_ledger.jsonl · seed_open_gaps（最多 2）· verify 后 CLOSED/OPEN
   DeliveryContract 挂在 engine_query 上 · kind=replan · runtime overlay · --eval

⬜ 闭环还没做（#10 合入了外形，不是合同）
   真 \(V_D\)：重算 risk_state / fingerprint / as_of，不是「subprocess 写出了 JSON」
   活的再规划（staged return / 改共享计划 / 停支；不是再打一次 engine_query）
   overlay 只给研究 profile（Verifier 现已吃 profile_hints.md）
   评测驱动下一轮（多于一条冻结日，失败可重开）
   引擎保持上游 pin，不要 fixtures/engine src+parquet
```

机器可读：`apodex_gap.json`。

## 当前基线

| 字段 | 值 |
| --- | --- |
| 评审 SHA | `7f3c893` *Merge pull request #10 from z26qin/aaron/unify-engine-surface* |
| 评审时间 | 2026-09-04 |
| 综合分 | **48 / 100**（verified_runtime） |
| `main` 上的提交 | 含 #2 / #5 / #6 / #7 / #9 / #10 |
| 刚合入 | [PR #9](https://github.com/z26qin/momentum-research-agent/pull/9) + [PR #10](https://github.com/z26qin/momentum-research-agent/pull/10)。探针 17/22 → 19/22。正式分 38→48 |

上一轮对 #10 的预估就是 48，并写了「不要按现状合入」。合入后正式分按预估落地；**阻断项全部还在 main 上**，没有因合入而消失。

## 分维

分数是相对 Apodex 该环节的完整度，不是相对「一个 CLI 研究 agent」的完成度。

| 维度 | 分 | 已有证据 | 仍缺 |
| --- | ---: | --- | --- |
| 能力缺口挖掘 | 42 | session `gaps[]` + 跨 session ledger + `--eval` 写回 `eval:{case_id}` | 分类是关键词；`SOURCE_QUALITY` 不种植；eval 去重后不能重开 |
| Task Pipeline | 26 | `followup_specs` + `seed_open_gaps` + 一个 `kind=replan` | 修旧 claim / 再打同一工具，不是新研究世界工厂 |
| Environment Scaling | 48 | 真 `run_mvp` subprocess；poisoned snapshot 不影响 pass | \(V_D\) 浅（写出 JSON 即 pass）；49MB vendor；`end is None` 跳过 pipeline |
| Agentic Coordination Scaling | 38 | verify → follow-up；第一波后 `maybe_replan` | 无 staged return、停支、异步介入；`pipeline_run is not True` 几乎必触发 |
| 非对称验证 | 38 | 独立 `Verifier` + static audit + conservative merge | overlay 漏进 `load_profile("verifier")`（相对 #7 回退）；无 statement-level 反例 |
| 轨迹学习 | 26 | `traces.jsonl` + `refresh_profile_hints` 从 OPEN gap 写 overlay | regex 抽 ticker，不是轨迹策略；冻结 profile 这点是对的 |
| 评测归因 | 32 | 单测 + `--eval` 一条 `2026-05-29 / normal` | 不是 working-capability bench；失败 `ENGINE_MOCK` 且不可重开 |

## 架构对照（相对论文，不是相对愿望）

Apodex 1.1 的工作能力合同是 Eq. (1)：

\[\mathcal{E}=(\mathcal{W},W_{0},q,\mathcal{A},\mathcal{T},\Omega,\mathbf{B},D,V_{D})\]

\(V_D(W_0,W_H,\tau_H)\)（Eq. 5）对照交付合同重算/对源/打断言。Agent Team（§3.2）要把分解写进**活的** task board，并在执行中：阶段性回传、改共享计划、停掉过时分支、接受 \(u_t\) 介入、用更窄的 verifier 打关键断言。FrontierAgent 把同一套东西落成：磁盘 task board、`/inputs|/workspace|/outputs` sandbox、可选 fast reporter、TUI 队列式干预。

本仓库刻意不做的（正确）：权重 SFT/RL、AgentBus、SpawnGuard、通用 Heavy-Duty Solver、LangChain 系。自我改进在这里是**系统级受控闭环**，不是模型改自己的权重。

当前运行路径：

```
CLI → Coordinator.run
        ├─ decompose()              仍要求任务 self-contained
        ├─ seed_from_ledger()       最多 2 个 kind=gap
        ├─ warm_engine()            同步 90s × 两个冻结日
        ├─ dispatch_all()
        ├─ maybe_replan()           再挂一个 momentum_analyst
        ├─ verify()                 load_profile("verifier") 会吃 overlay
        ├─ resolve_consumed_gaps()
        ├─ follow_up()              至多一轮
        ├─ verify()
        └─ synthesize()
```

相对 Apodex / FrontierAgent，#10 对齐的是**环境外形**（可执行 `run_mvp` 世界）和**账本段**（gap → 下一 session 任务）。没有对齐的是协调段和验证段：

| Apodex / FrontierAgent | 本仓库现在 |
| --- | --- |
| 活 task board：分支回传改共享计划 | 磁盘 `task_board.json`；`decompose.md` 仍要求 *without seeing other tasks' results* |
| staged return / 停过时支 / \(u_t\) | `kind=replan` = 第一波后再打一次 `engine_query(end=2026-05-29)` |
| \(V_D\) 对照 \(D\) 重算或对源 | `pipeline_pass()` = subprocess 写出了带 `overall_risk_state` 的 JSON |
| Statement Review 不吃生产记忆 | `load_profile` 无条件拼 `profile_hints.md`，Verifier 走同一条 |
| 一份 run 目录、一份 trace | `traces.jsonl` 唯一（#10 删掉第二份 log）——这对 |
| 环境是可 pin 的世界，不是第二个产品树 | `fixtures/engine` 76 文件 / 49.9MB src+parquet |
| 评测失败进 Task Pipeline | `--eval` 一条 normal 日；`append_gaps` 按 `evidence_id` 永久去重 |

`should_replan` / `maybe_replan` **不算** `live_replan`。探针诚实：协调维仍缺 `replan_blocked` / `staged_return` / `class AgentBus`。

## 最近能真正动针的下一刀

#10 已经在 main。不要再加 profile，也不要再扩 vendor。下一刀是**收合同**，不是再铺一层闭环外形。

1. Engine 保持 **subprocess + 上游 pin**（`MOMENTUM_ENGINE_DIR` / sibling）。本仓库最多留 manifest + 小 JSON 金样。把 `fixtures/engine/src` 和 38MB `sp500_prices.parquet` 移出去。
2. \(V_D\) 独立于 subprocess 退出：重算 `risk_state` / fingerprint / as_of；crowding/unwind **断言**由 verifier 打。
3. `engine_query` 无 `end` 时显式解析最新 as-of 或 fail-closed。不能静默跳过 pipeline。Replan 只在 BLOCKED 或真 mock / `verdict=fail`。作业应改共享计划，不是再打一次同一工具。
4. Overlay 只给研究 profile；`Verifier` 不吃 `profile_hints.md`。`load_profile(..., apply_overlay=False)` 即可。
5. `--eval` 至少两条冻结日（含非 `normal`），同一 `evidence_id` 可重开。失败用 `engine_freshness`，不要一律 `ENGINE_MOCK`。
6. `warm_engine()` 改 `asyncio.to_thread`，缓存进 session `engine_runs/`，只在有人请求该 as-of 时再跑。

`AGENTS.md` 明确不做：LangChain/LangGraph/CrewAI、Web UI、Docker、数据库、MCP、AgentBus、无界 follow-up、对 DeepSeek 权重做 SFT/RL。

## PR #10 已合入

https://github.com/z26qin/momentum-research-agent/pull/10 于 2026-09-04 合入 `main`（`7f3c893`，head `e490aa5`）。live `run_mvp` + 浅 \(V_D\) + `kind=replan` + overlay + `--eval` + 49MB PIT pack。三处收口值得留：单一 `resolve_engine_root`、只读 `traces.jsonl`、`run()`/`resume()` 共用 `_dispatch_wave`。正式分 38→48。阻断项见上。

## PR #9 已合入

https://github.com/z26qin/momentum-research-agent/pull/9 于 2026-09-04 合入（`67692b3`）。#10 是它的超集；分数记在 #10。

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

## Probe 快照（2026-09-04 18:55 UTC）

可复跑：`python3 scripts/probe_apodex_gap.py origin/main`

| 维度 | main 命中 | 仍缺 |
| --- | --- | --- |
| 缺口挖掘 | Task + BLOCKED + EvidenceVerdict + capability_ledger | — |
| Task Pipeline | followup_specs, TaskKind.FOLLOWUP, gap_seed | 新环境工厂 |
| 环境缩放 | engine_adapter + **delivery_verifier** + mock 回退 | \(V_D\) 深度（探针亮灯 ≠ 合同） |
| 协调缩放 | TaskBoard + `follow_up()` | live replan / staged return |
| 非对称验证 | Verifier + static_audit + conservative merge | overlay 漏进 verifier；无 Statement Review |
| 轨迹学习 | trajectory_log + **prompt_evolution** | 轨迹策略（现为 regex overlay） |
| 评测归因 | 单测 + verifier tests + `--eval` | working-capability 基准 |

探针 19/22。相对 #7 的 17/22，多了 `delivery_verifier` 和 `prompt_evolution`。`live_replan` / `new_environment_factory` / `working_capability_bench` 仍缺。`live_replan` 不把 `should_replan` / `maybe_replan` 算命中——这是对的。

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
| 2026-09-04 | `7f3c893` | 48 | PR #9+#10 合入。live `run_mvp` + 浅 \(V_D\) + replan + overlay + `--eval` + 49MB vendor。探针 19/22。正式分 38→48。先前对 #10 的阻断项全部落地：浅 \(V_D\)、过宽 replan、overlay 进 verifier、vendor 树、同步 90s warm。 |
