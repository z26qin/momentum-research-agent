# Agent operating manual

This repository is a thin, purpose-built multi-agent research system for US equity momentum tail-risk. Read this file before changing orchestration, prompts, or tools.

## Architecture

```
Question
   ↓
Coordinator
   ↓
TaskBoard
   ↓
GAP seed (at most 2 kind=gap from reports/gap_ledger.jsonl)
   ↓
engine warm (subprocess run_mvp, ~90s cache)
   ↓
parallel SubAgents
   ↓
optional one kind=replan (BLOCKED / mock / stale / V_D fail)
   ↓
bounded ReAct runtime
   ↓
explicit authorized tools
   ↓
Evidence[]
   ↓
ResearchReport JSON
   ↓
independent Verifier  (static audit + bounded ReAct re-check)
   ↓
append verification.gaps → reports/gap_ledger.jsonl
   ↓
optional one-round follow-up  (rejected / unchecked only)
   ↓
VerificationReport JSON
   ↓
Coordinator synthesis
```

`summary` is for humans. `findings: list[Evidence]` is the machine-readable source of truth. The verifier does not produce new research claims; it only judges existing `evidence_id`s. Conservative merge: static REJECTED/UNCHECKED cannot be overwritten to VERIFIED by a more optimistic LLM.

`verification.json` is the per-session momentum gap ledger: `gaps[]` (rejected/unchecked/missing/unanswered/engine_mock) plus `traces[]` of replayable `engine_query` / `web_search` calls. Live search is stored-observation replay; engine snapshots replay from `source_path` when present.

After verify, those `gaps[]` are appended to the cross-session file `reports/gap_ledger.jsonl` (deduped by `evidence_id`, status `OPEN` / `CONSUMED` / `CLOSED`). The next session classifies each row as `crowding` / `unwind_crash` / `engine_freshness` / `source_quality`. After decompose and before dispatch, `seed_from_ledger()` plants at most 2 `kind=gap` tasks (`crowding` → `flow_analyst`, unwind/engine → `momentum_analyst`) and marks those rows `CONSUMED`. After this session verifies those planted tasks, the same rows become `CLOSED` (VERIFIED / no longer `ENGINE_MOCK`) or go back to `OPEN` (still rejected / unchecked / mock). This is not a second follow-up and not AgentBus.

Follow-up is one bounded extra dispatch (default max 2 tasks) using the original analyst profiles. It does not reopen verified items, does not loop, and is skipped on a session that already has `kind=followup` tasks or a completed synthesis. After the first dispatch wave, at most one `kind=replan` may run (BLOCKED, or this session's `engine_query` was mock / stale / V_D fail). Replan is not follow-up and not AgentBus.

`engine_query` prefers a **live** `run_mvp` via subprocess:

```bash
python scripts/run_monitor.py --as-of-date YYYY-MM-DD --output-json …
```

Path: `require_cached_inputs()` → `run_compact_assessment()` → `run_mvp()` reading `data/processed/*.parquet`. This repo must not `from src.mvp import` or `import momentum_crash`. `MOMENTUM_ENGINE_DIR` / a sibling checkout wins when present; otherwise the vendored PIT pack at `fixtures/engine` (commit `99b0688`) is used. If `MOMENTUM_ENGINE_DIR` is set to a missing path, do not fall back to the bundle. File snapshots and `local_dm` cannot `delivery_contract.verdict=pass`. Only `pipeline_run=True` from live `run_mvp` can. Query timeout ~8s; Coordinator warm ~90s. `--eval` calls `engine_query(end="2026-05-29")` with no DeepSeek and writes failures as `eval:{case_id}` into the gap ledger plus `reports/prompt_evolution.json` / `profile_hints.md`. Committed `profiles/*.md` stay frozen; overlays are runtime-only.

## Artifacts

```
reports/gap_ledger.jsonl                  # cross-session OPEN/CONSUMED/CLOSED gaps
reports/prompt_evolution.json             # runtime overlay rules (not weight training)
reports/profile_hints.md                  # appended to frozen profiles at load time
reports/{YYYYMMDD}_{HHmmss}_{8-char-hex}/
  task_board.json
  sub_reports/{task_id}_{profile}.json    # source of truth
  sub_reports/{task_id}_{profile}.md      # human rendering
  traces.jsonl                       # append-only engine_query / web_search log
  trajectory.jsonl                   # all-tool previews for overlay
  engine_runs/                       # optional session cache; pipeline cache lives on the engine root
  verification.json                  # per-session momentum gap ledger (gaps + replayable traces + verdicts)
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

No AgentBus, SpawnGuard, verifier-of-the-verifier, web UI, Docker, database, MCP server, or extra agent frameworks. Follow-up research is the one bounded in-session round above — do not turn it into an unbounded loop. Cross-session gap seed plants at most 2 `kind=gap` tasks; replan is at most one `kind=replan` after the first wave. Copying `structured_snapshot.json` is not a V_D pass path.
