# Agent operating manual

This repository is a thin, purpose-built multi-agent research system for US equity momentum tail-risk. Read this file before changing orchestration, prompts, or tools.

## Architecture

```
Question
   ↓
Coordinator.warm_engine  (optional live run_monitor.py → session engine_runs/)
   ↓
Coordinator.decompose  (injects gap_ledger + prior trajectory briefs)
   ↓
GAP seed (at most 2 kind=gap from reports/gap_ledger.jsonl)
   ↓
parallel SubAgents  (+ reports/profile_hints.md overlay; engine_query hits warm cache)
   ↓
optional one-task replan if BLOCKED or engine_query was mock/stale/V_D fail
   ↓
Evidence[] / ResearchReport JSON  +  trajectory.jsonl + traces.jsonl
   ↓
independent Verifier  (compiles verification.json gaps[] / traces[])
   ↓
append verification.gaps → reports/gap_ledger.jsonl
   ↓
optional one-round follow-up  (rejected / unchecked only)
   ↓
Coordinator synthesis
```

`summary` is for humans. `findings: list[Evidence]` is the machine-readable source of truth. The verifier does not produce new research claims; it only judges existing `evidence_id`s. Conservative merge: static REJECTED/UNCHECKED cannot be overwritten to VERIFIED by a more optimistic LLM.

`verification.json` is the in-session momentum gap ledger: `gaps[]` (rejected/unchecked/missing/unanswered/engine_mock) plus replayable `engine_query` / `web_search` `traces[]`. Live search is stored-observation replay; engine snapshots replay from `source_path` when present.

After verify, those `gaps[]` are appended to the cross-session file `reports/gap_ledger.jsonl` (deduped by `evidence_id`, status `OPEN` / `CONSUMED`). The next session classifies each row as `crowding` / `unwind_crash` / `engine_freshness` / `source_quality`. After decompose and before dispatch, `seed_from_ledger()` plants at most 2 `kind=gap` tasks (`crowding` → `flow_analyst`, unwind/engine → `momentum_analyst`) and marks those rows `CONSUMED`. This is not a second follow-up and not AgentBus.

Follow-up is one bounded extra dispatch (default max 2 tasks) using the original analyst profiles. It does not reopen verified items, does not loop, and is skipped on a session that already has `kind=followup` tasks or a completed synthesis. AgentBus is still out of scope.

Replan is a different one-shot: after the first dispatch wave, if a task is BLOCKED at runtime **or** this session's `engine_query` was mock / stale / `V_D` fail, the Coordinator may add at most one `kind=replan` replacement and dispatch it. That is not a second follow-up and not an AgentBus.

Cross-session gaps are different: after verification, rejected/unchecked claims are appended to `reports/gap_ledger.jsonl`. The *next* run may seed at most 2 `kind=gap` tasks from open rows, then mark those rows consumed. Decompose also sees a `failure_brief` of open/recent gaps. That is not a second follow-up round inside the same session.

`engine_query` prefers a warmed live PIT run of `momentum-tail-risk-monitor` (`scripts/run_monitor.py` via `MOMENTUM_ENGINE_DIR` or a sibling checkout) when Coordinator.warm_engine cached it under `session_dir/engine_runs/`. Matching JSON snapshots — including the frozen 2026-05-29 / 2026-06-30 cases vendored at `fixtures/engine/` — are the fast path. If neither exists, it runs a local Daniel–Moskowitz scorer on SPY + ticker closes (24m bear + 6m vol → `risk_state`; 1m drawdown → unwind regime). Labeled mock only if prices are unavailable. Every payload includes a delivery contract `V_D` (`pass` | `pass_with_caveats` | `fail`). File snapshots and `local_dm` cannot `pass` without caveats; a live pipeline run can. Frozen eval (`momentum-research-agent --eval`) grades DM/crowding/unwind fixtures — including the bundled snapshot and the pipeline contract — and appends failures to the ledger.

## Artifacts

```
reports/gap_ledger.jsonl                 # cross-session OPEN/CONSUMED gaps
reports/profile_hints.md                 # generated overlay from ledger + traces
reports/prompt_evolution.json            # capability/trace rules used in that overlay
reports/{YYYYMMDD}_{HHmmss}_{8-char-hex}/
  task_board.json
  trajectory.jsonl                       # all tool calls (preview)
  traces.jsonl                           # full engine_query / web_search observations
  engine_runs/{as_of}.json               # warmed live PIT assessment (when pipeline exists)
  sub_reports/{task_id}_{profile}.json    # source of truth
  sub_reports/{task_id}_{profile}.md      # human rendering
  verification.json                      # session gap ledger (gaps + traces + verdicts)
  verification.md
  synthesis.md
  synthesis.json
```

Resume loads JSON first. Legacy Markdown-only sessions become a low-confidence `partial` report; structure is not pretended to survive.

## Runtime guarantees

Each sub-agent run is bounded by `LoopBudget`:

- `max_turns` (default 8)
- `overall_deadline_s` (default 45) via `time.monotonic()`
- `llm_timeout_s` (default 20)
- `tool_timeout_s` (default 10)

Every LLM/tool call uses `min(configured_timeout, remaining_overall_deadline)`. `asyncio.CancelledError` is never converted into a tool observation.

## Tool authorization (fail closed)

```
registered tool  !=  authorized tool for this agent
```

- Unknown profile → `UnauthorizedTool`, no default capabilities
- Known profile → explicit `PROFILE_TOOLS` allowlist
- Model-requested tools not in that allowlist are not executed
- `shell` remains implemented but is not on any research or verifier allowlist
- `verifier` has tools but is **not** a research profile. Decompose/dispatch cannot assign it. Coordinator calls `Verifier` separately.

Do not add a profile to `DEFAULT_TOOLS` as a fallback. `DEFAULT_TOOLS` is documentation of the research tool set, not an authorization backdoor.

## Rules of the road

1. **No LangChain / LangGraph / CrewAI.** Raw `AsyncOpenAI` against `https://api.deepseek.com`.
2. **Prompts are markdown files.** Edit `coordinator/prompts/*.md` and `agents/profiles/*.md`.
3. **Every TaskBoard mutation saves.**
4. **Sub-agent failure is not coordinator failure.** Typed runtime errors mark the task `BLOCKED`.
5. **Structured output is Pydantic.** ResearchReport / Evidence / decompose / synthesize.
6. **Per-agent usage is local.** Coordinator merges `UsageSummary` after each run. Do not subtract global totals.
7. **Keep it flat.** Dict registry, direct imports, no plugin frameworks.

## Adding a tool

1. Create `src/momentum_research_agent/tools/your_tool.py`.
2. Decorate an `async def your_tool(**kwargs) -> str` with `@register_tool`.
3. Import the module in `tools/__init__.py` so registration happens.
4. Add the name to the relevant `PROFILE_TOOLS` allowlists. Registration alone does not authorize it.
5. Mention the tool in the profile markdown that should use it.

## Adding an analyst profile

1. Write `src/momentum_research_agent/agents/profiles/{name}.md`.
2. Copy or symlink it into repo-root `profiles/`.
3. Add `{name}` to the decompose prompt's allowed profile list **and** to `PROFILE_TOOLS`.
4. Unknown names fail closed. Do **not** add `verifier` to the decompose list; it is invoked only by the Coordinator after research completes.

## Tests

```bash
uv sync --group dev
uv run pytest
```

Do not hit the live DeepSeek API in unit tests.

## What not to build here

No AgentBus, SpawnGuard, verifier-of-the-verifier, web UI, Docker, database, MCP server, or extra agent frameworks. Follow-up research is the one bounded round above — do not turn it into an unbounded loop. Replan is the one BLOCKED retry above. Cross-session gap seed plants at most 2 `kind=gap` tasks from `reports/gap_ledger.jsonl`; it is not a second follow-up.
