# Agent operating manual

This repository is a thin, purpose-built multi-agent research system for US equity momentum tail-risk. Read this file before changing orchestration, prompts, or tools.

## Architecture

```
Question
   ↓
Coordinator.decompose  (injects gap_ledger + prior trajectory briefs)
   ↓
TaskBoard  (+ optional GAP tasks from reports/gap_ledger.jsonl)
   ↓
parallel SubAgents  (+ reports/profile_hints.md overlay)
   ↓
optional one-task replan if a research task is BLOCKED
   ↓
Evidence[] / ResearchReport JSON  +  session trajectory.jsonl
   ↓
independent Verifier
   ↓
append rejected/unchecked to gap_ledger.jsonl
   ↓
optional one-round follow-up
   ↓
Coordinator synthesis
```

`summary` is for humans. `findings: list[Evidence]` is the machine-readable source of truth. The verifier does not produce new research claims; it only judges existing `evidence_id`s. Conservative merge: static REJECTED/UNCHECKED cannot be overwritten to VERIFIED by a more optimistic LLM.

Follow-up is one bounded extra dispatch (default max 2 tasks) using the original analyst profiles. It does not reopen verified items, does not loop, and is skipped on a session that already has `kind=followup` tasks or a completed synthesis. AgentBus is still out of scope.

Replan is a different one-shot: after the first dispatch wave, if a task is BLOCKED at runtime, the Coordinator may add at most one `kind=replan` replacement and dispatch it. That is not a second follow-up and not an AgentBus.

Cross-session gaps are different: after verification, rejected/unchecked claims are appended to `reports/gap_ledger.jsonl`. The *next* run may seed at most 2 `kind=gap` tasks from open rows, then mark those rows consumed. Decompose also sees a `failure_brief` of open/recent gaps. That is not a second follow-up round inside the same session.

`engine_query` reads JSON artifacts from `momentum-tail-risk-monitor` (`MOMENTUM_ENGINE_DIR`, `MOMENTUM_ENGINE_SNAPSHOT`, or a sibling checkout). It does not import or run that pipeline. No snapshot → labeled mock. Every payload includes a delivery contract `V_D` (`pass` | `pass_with_caveats` | `fail`). Frozen eval (`momentum-research-agent --eval`) grades DM/crowding/unwind fixtures and appends failures to the ledger.

## Artifacts

```
reports/gap_ledger.jsonl                 # cross-session rejected/unchecked claims
reports/profile_hints.md                 # generated overlay from ledger + traces
reports/{YYYYMMDD}_{HHmmss}_{8-char-hex}/
  task_board.json
  trajectory.jsonl                       # tool calls for this session
  sub_reports/{task_id}_{profile}.json    # source of truth
  sub_reports/{task_id}_{profile}.md      # human rendering
  verification.json                      # independent Evidence[] audit
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

No AgentBus, SpawnGuard, verifier-of-the-verifier, web UI, Docker, database, MCP server, or extra agent frameworks. Follow-up research is the one bounded round above — do not turn it into an unbounded loop. Replan is the one BLOCKED retry above. The gap ledger only seeds the next session, and is capped.
