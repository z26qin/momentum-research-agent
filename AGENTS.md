# Agent operating manual

This repository is a thin, purpose-built multi-agent research system for US equity momentum tail-risk. Read this file before changing orchestration, prompts, or tools.

## Architecture

```
CLI → Coordinator.run(question)
        ├─ decompose()     deepseek-reasoner + prompts/decompose.md
        ├─ dispatch_all()  asyncio.gather of SubAgent.run
        │                    └─ react_loop() + profile markdown + tools
        └─ synthesize()    deepseek-reasoner + prompts/synthesize.md
```

State lives on disk, not in memory:

- `reports/{session_id}/task_board.json` — source of truth
- `reports/{session_id}/sub_reports/{task_id}_{profile}.md`
- `reports/{session_id}/synthesis.md` and `synthesis.json`

Session IDs are `{YYYYMMDD}_{HHmmss}_{8-char-hex}`.

## Rules of the road

1. **No LangChain / LangGraph / CrewAI.** Raw `AsyncOpenAI` against `https://api.deepseek.com`.
2. **Prompts are markdown files.** Edit `coordinator/prompts/*.md` and `agents/profiles/*.md` (also mirrored at repo-root `profiles/`). Do not inline long prompts in Python.
3. **Every TaskBoard mutation saves.** If you add a new status change, call `save()`.
4. **Sub-agent failure is not coordinator failure.** `asyncio.gather(..., return_exceptions=True)`, mark the task `BLOCKED`, continue, and mention the gap in synthesis.
5. **Structured output is Pydantic.** Decompose / synthesize must parse with `model_validate_json`. Retry once with the validation error.
6. **Keep it flat.** Dict registry, direct imports, no plugin frameworks.

## Client pattern

```python
from openai import AsyncOpenAI
import os

client = AsyncOpenAI(
    api_key=os.environ["DEEPSEEK_API_KEY"],
    base_url="https://api.deepseek.com",
)
```

Defaults: `deepseek-chat` for sub-agents, `deepseek-reasoner` for decompose/synthesize. Override with `--model`, `--coordinator-model`, or env `SUB_AGENT_MODEL` / `COORDINATOR_MODEL`. If those aliases 404 (retired July 2026), switch to `deepseek-v4-flash` / `deepseek-v4-pro`.

## Adding a tool

1. Create `src/momentum_research_agent/tools/your_tool.py`.
2. Decorate an `async def your_tool(**kwargs) -> str` with `@register_tool`.
3. Import the module in `tools/__init__.py` so registration happens.
4. Add the name to `DEFAULT_TOOLS` and the relevant `PROFILE_TOOLS` lists.
5. Mention the tool in the profile markdown that should use it.

## Adding an analyst profile

1. Write `src/momentum_research_agent/agents/profiles/{name}.md` (keep it under ~40 lines).
2. Copy or symlink it into repo-root `profiles/`.
3. Add `{name}` to the decompose prompt's allowed profile list.
4. Add a `PROFILE_TOOLS` entry.

## Tests

```bash
uv sync --group dev
uv run pytest
```

Phase 1 coverage is the task board, the ReAct loop, and the coordinator file-writing flow. Do not hit the live DeepSeek API in unit tests.

## What not to build here

No web UI, Docker, database, MCP server, or extra agent frameworks. Files and a CLI are the product.
