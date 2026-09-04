# Momentum Research Agent

Multi-agent investigation system for US equity momentum tail-risk. A coordinator decomposes a research question, runs independent analyst sub-agents in parallel, and synthesizes a structured PM brief.

This is an original, purpose-built orchestration layer. It sits on top of a deterministic momentum tail-risk engine (Daniel–Moskowitz risk state, FINRA/GDELT overlays, triggered evidence). `engine_query` prefers a Coordinator-warmed `scripts/run_monitor.py` PIT run from `momentum-tail-risk-monitor` when that checkout is available, otherwise the frozen JSON snapshots in `fixtures/engine/` (2026-05-29 / 2026-06-30), otherwise a local DM scorer on SPY + ticker closes, and falls back to labeled mock data only if prices are unavailable.

## Architecture

```
question
   │
   ▼
Coordinator (deepseek-reasoner)
   ├─ engine warm → optional live run_monitor.py into session engine_runs/ (90s budget)
   ├─ decompose → TaskBoard (disk; sees prior gap ledger + traces)
   ├─ gap seed  → at most 2 kind=gap tasks from reports/gap_ledger.jsonl
   ├─ dispatch  → bounded SubAgents in parallel (deepseek-chat, ReAct + allowlisted tools)
   │                └─ ResearchReport { findings: Evidence[], summary, status }
   ├─ replan    → at most one kind=replan task if a research task is BLOCKED or engine_query was mock/stale/V_D fail
   ├─ verify    → independent Verifier (static audit + ReAct re-check of Evidence[])
   ├─ append    → verification.gaps → reports/gap_ledger.jsonl (OPEN / CONSUMED / CLOSED)
   ├─ resolve   → planted CONSUMED rows become CLOSED or OPEN again
   ├─ follow-up → at most one extra dispatch on rejected/unchecked evidence
   └─ synthesize → reports/{session}/synthesis.md
```

`ResearchReport.findings` is a list of typed `Evidence` objects (the machine-readable source of truth). `summary` is the human-readable view. No LangChain, LangGraph, or CrewAI.

## Setup

Requires Python 3.12+ and [uv](https://docs.astral.sh/uv/).

```bash
uv sync --group dev
cp .env.example .env
# set DEEPSEEK_API_KEY
# optionally SERPER_API_KEY or TAVILY_API_KEY for web_search
# optionally MOMENTUM_ENGINE_DIR pointing at momentum-tail-risk-monitor
```

## Usage

```bash
uv run momentum-research-agent "Is the recent NVDA selloff a momentum crash signal or a healthy rotation?"

uv run momentum-research-agent --mode single "Analyze NVDA credit risk"

uv run momentum-research-agent --eval
```

Flags: `--mode team|single`, `--session-dir`, `--resume`, `--max-sub-agents`, `--model`, `--coordinator-model`, `--verbose`, `--eval`.

On startup the CLI prints a Rich banner, a decomposition table, live task-board updates during dispatch, a synthesis panel, a token/cost summary, and the session path.

## Session artifacts

Each run writes `reports/{YYYYMMDD}_{HHmmss}_{8-char-hex}/`, plus a cross-session `reports/gap_ledger.jsonl`:

| File | Purpose |
| --- | --- |
| `reports/gap_ledger.jsonl` | Cross-session OPEN/CONSUMED/CLOSED gaps (deduped by `evidence_id`) |
| `task_board.json` | Full task history with timestamps |
| `trajectory.jsonl` | All tool calls for this session (preview) |
| `traces.jsonl` | Full `engine_query` / `web_search` observations for replay |
| `sub_reports/{task_id}_{profile}.json` | Canonical `ResearchReport` (Evidence[]) |
| `sub_reports/{task_id}_{profile}.md` | Human-readable rendering of the same report |
| `verification.json` / `verification.md` | Session gap ledger: `gaps[]` + replayable `traces[]` + verdicts |
| `synthesis.md` / `synthesis.json` | Final PM brief |

Rejected/unchecked claims are also appended to `reports/gap_ledger.jsonl` (cross-session). The next team run may seed at most two `kind=gap` tasks from open rows. Decompose and sub-agents also read a generated `reports/profile_hints.md` overlay from that ledger and prior traces.

`--resume` reloads JSON reports first. Markdown-only leftovers from older sessions become a low-confidence compatibility report.

## Runtime bounds

Each sub-agent is capped by `LoopBudget`: 8 ReAct turns, 45s overall deadline, 20s per LLM call, 10s per tool. Cancellation (`asyncio.CancelledError`) propagates. Unknown analyst profiles and off-allowlist tools fail closed. `shell` is not part of normal research capabilities.

After verification, the coordinator may dispatch at most one extra follow-up round (default 2 tasks) for `rejected` / `unchecked` evidence, then re-verify once. Verified items are not reopened. `--mode single` does not follow up.

The next session may plant at most 2 `kind=gap` tasks from `reports/gap_ledger.jsonl` after decompose (`crowding` → `flow_analyst`, unwind/engine → `momentum_analyst`). After that session verifies the planted tasks, rows become `CLOSED` or go back to `OPEN`. That is not a second follow-up. After the first dispatch wave, at most one `kind=replan` task may retry a BLOCKED runtime failure or a mock/stale/`V_D`-fail engine_query.

`--eval` grades frozen Daniel–Moskowitz / crowding / unwind fixtures (including the bundled 2026-05-29 snapshot and delivery contract `V_D`) and appends failures to `reports/gap_ledger.jsonl`. It does not call DeepSeek.

## Tools

| Tool | Behavior |
| --- | --- |
| `web_search` | Serper, then Tavily. Clear error if neither key is set. |
| `file_reader` | `.md` `.txt` `.csv` (first 100 rows) `.json`. Refuses paths outside the project. |
| `engine_query` | Prefers a Coordinator-warmed live `scripts/run_monitor.py` PIT run; matching JSON snapshots (including `fixtures/engine` frozen 2026-05-29 / 2026-06-30) are the fast path; else a local DM scorer on SPY + ticker closes; labeled mock only if all three fail. Attaches `delivery_contract` `V_D`. Live pipeline can `pass`; snapshots/`local_dm`/mock cannot. |
| `market_data` | yfinance OHLCV table (period default `3mo`). |
| `shell` | Implemented but **not** assigned to research profiles. Not used in normal flows. |

## Models and cost

Client initialization is always:

```python
client = AsyncOpenAI(
    api_key=os.environ["DEEPSEEK_API_KEY"],
    base_url="https://api.deepseek.com",
)
```

Default model IDs follow the original DeepSeek aliases (`deepseek-chat` for sub-agents, `deepseek-reasoner` for decompose/synthesize). Those aliases were retired in July 2026; if calls fail, set:

```bash
SUB_AGENT_MODEL=deepseek-v4-flash
COORDINATOR_MODEL=deepseek-v4-pro
```

Cost estimates use published USD / 1M-token rates (cache-hit and peak/off-peak ignored):

| Model | Input | Output |
| --- | ---: | ---: |
| deepseek-chat | $0.27 | $1.10 |
| deepseek-reasoner | $0.55 | $2.19 |
| deepseek-v4-flash | $0.22 | $0.66 |
| deepseek-v4-pro | $0.66 | $1.98 |

See [DeepSeek pricing](https://api-docs.deepseek.com/quick_start/pricing).

## Tests

```bash
uv run pytest
```

## Layout

See `AGENTS.md` for how to add tools, profiles, and prompts without touching orchestration code.

An example compiled session ledger (engine snapshot + search observation + open gaps) lives in `examples/nvda_momentum_gap_ledger.json`.
