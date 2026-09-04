# Coding-agent task: real PIT `run_mvp` + closed loop from `main`

Give this file to a **coding** agent. The review agent does not implement it.

**Ignore [PR #3](https://github.com/z26qin/momentum-research-agent/pull/3).** Do not rebase it, do not push to `cursor/momentum-gap-loop-6ca3`, and do not use its JSON snapshot-copy stub as the \(V_D\) pass path.

---

## Repo and branch

- Repo: `https://github.com/z26qin/momentum-research-agent`
- Base: `origin/main` (after PR #7; tip `5e970ef` as of 2026-09-04). Run `git fetch origin main` first.
- New branch: `cursor/pit-mvp-vd-6ca3` (`cursor/` prefix + `-6ca3` suffix).
- Open a **new PR into `main`**. Do not update PR #3.
- Code and commit messages in English. Do not rewrite committed `profiles/*.md`.

---

## Goal

Vertical closed-loop research agent: Apodex-shaped **managed** capability loop × **only** US equity momentum factor risk (Daniel–Moskowitz crash / crowding / unwind).

### Already on `main`

- TaskBoard; decompose / parallel dispatch / synthesize
- Independent Verifier
- One in-session follow-up (max 2 tasks)
- `reports/gap_ledger.jsonl`; next run plants at most 2 `kind=gap` tasks
- After verify: planted `CONSUMED` → `CLOSED` or back to `OPEN`

### This PR must add (none of these are on `main`)

1. **True DM engine + \(V_D\)** (the core; JSON file-copy is not the engine)
2. Live replan (at most one `kind=replan`)
3. Prompt evolution from trajectories (runtime overlay only; no weight training)
4. `--eval` writeback into the gap ledger and overlay

---

## True engine (hard requirements)

The live engine is `https://github.com/z26qin/momentum-tail-risk-monitor` @ **`99b0688`**.

Entry point:

```bash
python scripts/run_monitor.py --as-of-date YYYY-MM-DD --output-json …
```

Path: `require_cached_inputs()` → `run_compact_assessment()` → **`run_mvp()`** reading `data/processed/*.parquet`.

`AGENTS.md`: **do not** `from src.mvp import` or `import momentum_crash` inside this repo. **Subprocess only.**

Declared processed inputs (`run_mvp` may need more; use whatever a real run actually requires):

- `market_features.parquet`
- `leg_risk_history.parquet`
- `french_research_factors_daily.parquet`
- `momentum_labels_h5.parquet`
- `momentum_labels_h20.parquet`

Do **not** vendor the whole ~188MB monitor tree. Do **not** add `sp500_prices.parquet` (~40MB) unless `run_mvp` fails without it.

**How:** in a monitor checkout, run the **upstream** `scripts/run_monitor.py` for `2026-05-29` and `2026-06-30`. Record missing parquets and `src/` modules. Vendor only that minimum PIT pack. Write `SOURCE.txt` with commit `99b0688` and the file list. `MOMENTUM_ENGINE_DIR` / a sibling checkout still wins when present.

### Anti-cheat

`engine_query("NVDA", end="2026-05-29")` with `MOMENTUM_DISABLE_PIPELINE` unset must return `pipeline_run=True` and `delivery_contract.verdict=pass`, and the state must come from `run_mvp`.

Regression: corrupt any `structured_snapshot.json` (wrong `risk_state`). The query must still return `run_mvp`’s `normal`, not the poisoned JSON.

**Using a stub that copies `structured_snapshot.json` to get \(V_D\) pass = fail this task.**

Unknown dates fail closed (stale snapshot / local DM / labeled mock) → `pass_with_caveats` or `fail` only. Timeouts: query ~8s, warm ~90s.

File snapshots and `local_dm` cannot \(V_D\) `pass`. Only `pipeline_run=True` from live `run_mvp` can.

---

## Rest of the loop (`main` does not have these)

You may **read** PR #3 for shape. Do **not** cherry-pick its JSON stub.

- **\(V_D\):** Pydantic delivery contract on every `engine_query` payload.
- **Replan:** after the first dispatch wave, at most one `kind=replan` (BLOCKED, or this session’s `engine_query` was mock / stale / \(V_D\) fail). Not a second follow-up. Not AgentBus.
- **Trajectory:** `trajectory.jsonl` (tool previews). Overlay accumulates ticker/as-of rules from failure markers and OPEN gaps into `reports/prompt_evolution.json` + `reports/profile_hints.md`. CLOSED gaps drop their rules. Committed profiles stay frozen.
- **`--eval`:** no DeepSeek. At least one case must actually `asyncio`-call `engine_query(end="2026-05-29")` and expect `pipeline_run=True` and \(V_D\) pass. Failures `append_gaps` (`eval:{case_id}`) and `refresh_profile_hints`.

Follow-up stays one round, max 2. No unbounded loop.

---

## Constraints (`AGENTS.md`)

- No LangChain / LangGraph / CrewAI. Prompts in markdown. Structured output is Pydantic. Every TaskBoard mutation `save()`.
- No web UI / Docker / database / MCP / AgentBus.
- Unit tests must not hit live DeepSeek. `python3 -m pytest` or `uv run pytest`.
- `prompt_memory` must not import `coordinator.gap_seed` at module top (circular import).
- If `MOMENTUM_ENGINE_DIR` is set to a missing path, do not silently fall back to bundled fixtures.

---

## Done when

- New PR targets `main`, not PR #3.
- After snapshot JSON is poisoned, \(V_D\) still passes and `risk_state` matches `run_mvp`.
- This repo does not import the monitor package.
- pytest is green.
- PR body lists the PIT pack files and sizes, and what is still out of repo (full processed tree, live downloads).
- **Do not merge.**

---

## Out of scope

- Standing Apodex scorecard (PR #1) unless a test needs it.
- Competing with user `aaron/` PRs.
- Changing DeepSeek model weights or committed analyst profiles.
