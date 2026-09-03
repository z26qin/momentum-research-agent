# Momentum Research Agent

Multi-agent investigation system for US equity momentum tail-risk. A coordinator decomposes a research question, runs independent analyst sub-agents in parallel, and synthesizes a structured PM brief.

This is an original, purpose-built orchestration layer. It sits on top of a deterministic momentum tail-risk engine (Daniel–Moskowitz risk state, FINRA/GDELT overlays, triggered evidence). `engine_query` is a mock until that engine is wired in.

## Architecture

```
question
   │
   ▼
Coordinator (deepseek-reasoner)
   ├─ decompose → TaskBoard (disk)
   ├─ dispatch  → SubAgents in parallel (deepseek-chat, ReAct + tools)
   └─ synthesize → reports/{session}/synthesis.md
```

No LangChain, LangGraph, or CrewAI. Raw OpenAI SDK calls against DeepSeek's OpenAI-compatible endpoint.

## Setup

Requires Python 3.12+ and [uv](https://docs.astral.sh/uv/).

```bash
uv sync --group dev
cp .env.example .env
# set DEEPSEEK_API_KEY
# optionally SERPER_API_KEY or TAVILY_API_KEY for web_search
```

## Usage

```bash
uv run momentum-research-agent "Is the recent NVDA selloff a momentum crash signal or a healthy rotation?"

uv run momentum-research-agent --mode single "Analyze NVDA credit risk"

uv run momentum-research-agent --resume 20260903_171500_ab12cd34
```

Flags: `--mode team|single`, `--session-dir`, `--resume`, `--max-sub-agents`, `--model`, `--coordinator-model`, `--verbose`.

On startup the CLI prints a Rich banner, a decomposition table, live task-board updates during dispatch, a synthesis panel, a token/cost summary, and the session path.

## Session artifacts

Each run writes `reports/{YYYYMMDD}_{HHmmss}_{8-char-hex}/`:

| File | Purpose |
| --- | --- |
| `task_board.json` | Full task history with timestamps |
| `sub_reports/{task_id}_{profile}.md` | One report per sub-agent |
| `synthesis.md` / `synthesis.json` | Final PM brief |

`--resume` reloads the board, retries unfinished tasks, and synthesizes if needed.

## Tools

| Tool | Behavior |
| --- | --- |
| `web_search` | Serper, then Tavily. Clear error if neither key is set. |
| `file_reader` | `.md` `.txt` `.csv` (first 100 rows) `.json`. Refuses paths outside the project. |
| `engine_query` | Deterministic mock risk state. `# TODO: wire to actual engine`. |
| `market_data` | yfinance OHLCV table (period default `3mo`). |
| `shell` | Project-cwd subprocess, 30s timeout, command printed first. |

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
