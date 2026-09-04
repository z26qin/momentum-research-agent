# Apodex 自我改进差距评分卡

常驻评审产物。每次 `main` 有新提交时更新 `last_reviewed_sha` 与各维分数。机器可读副本见同目录 `apodex_gap.json`。

对照对象是 Apodex 1.1 的**受控能力开发循环**（[论文](https://arxiv.org/html/2608.23283) §2.5 / 图 2），不是模型自己改权重：

```
真实失败 / 评测错误 / 用户反馈
        ↓
  能力缺口分类
        ↓
  Task Pipeline（下一批任务）
        ↓
  Environment Scaling + Agentic Coordination Scaling
        ↓
  可回放轨迹 → SFT / agentic RL
        ↓
  评测与失败归因 → 下一轮
```

本仓库绑定冻结的 DeepSeek API，没有权重训练。可对齐的上限是**系统级**自我改进：从 session 进化 prompt、profile、工具和任务模板。

## 当前基线

| 字段 | 值 |
| --- | --- |
| 评审 SHA | `ef03fa5` *Add multi-agent momentum tail-risk research skeleton.* |
| 评审时间 | 2026-09-04 |
| 综合分 | **8 / 100**（scaffold_only） |
| `main` 上的提交数 | 1 |
| 未合入、会动针的 PR | [#2](https://github.com/z26qin/momentum-research-agent/pull/2) 预估合入后 **~22 / 100**（见下） |

`main` 分数在合入前不改。下面「分维」只描述 `ef03fa5`。

## 分维

分数是相对 Apodex 该环节的完整度，不是相对「一个 CLI 研究 agent」的完成度。

| 维度 | 分 | 已有证据 | 仍缺 |
| --- | ---: | --- | --- |
| 能力缺口挖掘 | 5 | `BLOCKED` + synthesis 里提缺口；`Task.error` 存异常字符串 | 无失败分类学；`reports/` 不当语料用 |
| Task Pipeline | 0 | `decompose.md` 从用户问题一次性拆 2–5 个独立任务 | 缺口不会变成下一批任务 |
| Environment Scaling | 10 | `web_search` / 只读 `file_reader` / `market_data` / 30s `shell` / mock `engine_query` | 无 \(D,V_D\)、无回放、engine 是 hash mock |
| Agentic Coordination Scaling | 20 | Coordinator 并行 + 磁盘 TaskBoard + `--resume` 崩溃恢复 | 无中途再规划、阶段性回传、停支、按问题生成角色、异步人工介入 |
| 非对称验证 | 5 | synthesize 要求保留异议；JSON schema 失败重试一次 | 无独立、更窄的 claim 攻击；综合者与生成者同上下文 |
| 轨迹学习 | 0 | 无 | 无 action/observation 日志，也无 prompt/工具自进化 |
| 评测归因 | 8 | task board / ReAct / coordinator 单测（不打 live API） | 无 working-capability 基准，测试失败不回流 |

## 架构对照（相对论文，不是相对愿望）

当前运行路径：

```
CLI → Coordinator.run
        ├─ decompose()     一次
        ├─ dispatch_all()  asyncio.gather，子任务互不可见
        └─ synthesize()    一次
```

Apodex 1.1 Agent Team 要把分解写进**活的** task board，并在执行中：阶段性回传、改共享计划、停掉过时分支、接受 \(u_t\) 介入、用更窄的 verifier 打关键断言。

本仓库已经对齐的外形：

- 磁盘 `task_board.json`（`TaskBoard` 每次 mutation 都 `save()`）
- lead / sub-agent 分裂
- 子代理失败不拖垮 coordinator（`return_exceptions=True`）

这是闭环的**前提**，不是闭环。

刻意相反的设计：`decompose.md` 要求任务 *self-contained, without seeing other tasks' results*。Apodex 的协调缩放依赖「一个分支的结果改写共享计划」。要靠近自我改进，这块必须改，而不是再加固定 profile。

## 最近能真正动针的下一刀

1. 每次 session 结束，从 `task_board.json` 和 sub-reports 抽出失败分类并落盘。
2. 让 task board 活起来：阶段性回传、coordinator 中途加/停/改任务。
3. 对 synthesis 的断言做独立、更窄的 statement review。
4. 把 `engine_query` 接到真引擎，否则没有可验证的交付合约。
5. 记录可回放的工具轨迹（任何后续学习的原料）。

在 1 和 5 之前加 analyst 或换 agent 框架，不会缩短与 Apodex 自我改进的距离。

`AGENTS.md` 明确不做：LangChain/LangGraph/CrewAI、Web UI、Docker、数据库、MCP、对 DeepSeek 权重做 SFT/RL。

## 未合入：PR #2 预评分

草稿 https://github.com/z26qin/momentum-research-agent/pull/2（`Tighten engine adapter and one-round follow-up`，head `5212820`）。**尚未进入 `main`，正式综合分仍是 8。**

它把运行路径改成：

```
decompose → dispatch → independent Verifier（static audit + 有界 ReAct）
        → 至多一轮 follow-up（只修 REJECTED / UNCHECKED）
        → 再 verify → synthesize
```

相对 Apodex 闭环，这是目前最接近「非对称验证 + 一次再规划」的补丁，不是自我改进循环本身。`AGENTS.md` 仍写明 AgentBus 不做、follow-up 禁止打成无界循环。

| 维度 | main | 合入后预估 | 依据 |
| --- | ---: | ---: | --- |
| 能力缺口挖掘 | 5 | 15 | `EvidenceVerdict` 的 rejected/unchecked 是 claim 级失败标签，不是能力级语料 |
| Task Pipeline | 0 | 8 | `followup_specs()` 从验证失败生成最多 2 个任务；不是新环境分布 |
| Environment Scaling | 10 | 22 | `engine_adapter` 读 monitor 快照；仍是文件适配器，无 \(V_D\)，无快照则 mock |
| Agentic Coordination Scaling | 20 | 32 | verify→follow-up→re-verify 是一次阶段性回传；调度中途仍不改共享计划 |
| 非对称验证 | 5 | 40 | 独立 `Verifier`：只判已有 `evidence_id`、静态审计 fail-closed、conservative merge。缺独立源类攻击与 statement-level counterexample |
| 轨迹学习 | 0 | 0 | 仍无 action/observation 回放，无 prompt/工具自进化 |
| 评测归因 | 8 | 18 | 新增 audit/verifier/followup/engine 单测；仍无 working-capability 基准 |
| **综合** | **8** | **~22** | 从 scaffold 迈到「有独立核验的研究运行时」；闭环后半段（任务工厂、轨迹学习）仍是 0 |

合入后仍缺、才会靠近自我改进的下一刀：把 rejected 证据收成跨 session 的能力缺口账本，并记录可回放轨迹。

## 更新规则

1. `git fetch origin main`，对 `last_reviewed_sha..origin/main` 做 diff。
2. 只给**被 diff 实际推进的维度**改分；没有新提交则只更新本文件的「无新提交」记录，不改分。
3. 同步改 `apodex_gap.json` 的 `last_reviewed_sha`、`last_reviewed_at` 和对应 `dimensions[].score_0_to_100`。
4. 在下面追加一行历史，不要改写旧行。

## 历史

| 日期 | SHA | 综合分 | 笔记 |
| --- | --- | ---: | --- |
| 2026-09-04 | `ef03fa5` | 8 | `main` 唯一提交：Phase 1 骨架。闭环六段均未作为代码存在。 |
| 2026-09-04 | `ef03fa5`（main 未变） | 8 | 预评草稿 PR #2：合入后综合分约 22。正式分不改，直到该 diff 进入 `main`。 |
