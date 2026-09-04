"""Frozen DM eval cases. No DeepSeek. Failures write back to the gap ledger."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from momentum_research_agent.coordinator.gap_seed import append_gaps
from momentum_research_agent.models.schemas import GapEntry, GapKind
from momentum_research_agent.state.prompt_memory import refresh_profile_hints
from momentum_research_agent.tools.engine_query import engine_query
from momentum_research_agent.tools.registry import ToolContext, set_tool_context


@dataclass(frozen=True)
class EvalCase:
    case_id: str
    ticker: str
    end: str
    expect_pipeline: bool
    expect_verdict: str
    expect_risk_state: str | None = None


CASES = (
    EvalCase(
        case_id="dm-2026-05-29",
        ticker="NVDA",
        end="2026-05-29",
        expect_pipeline=True,
        expect_verdict="pass",
        expect_risk_state="normal",
    ),
)


def _failures_from_result(case: EvalCase, payload: dict[str, Any] | None, error: str | None) -> list[GapEntry]:
    if error:
        return [
            GapEntry(
                kind=GapKind.ENGINE_MOCK,
                claim=f"eval {case.case_id} failed: {error}",
                notes="--eval writeback",
                evidence_id=f"eval:{case.case_id}",
            )
        ]
    assert payload is not None
    contract = payload.get("delivery_contract") if isinstance(payload.get("delivery_contract"), dict) else {}
    problems: list[str] = []
    if case.expect_pipeline and payload.get("pipeline_run") is not True:
        problems.append("pipeline_run was not True")
    if contract.get("verdict") != case.expect_verdict:
        problems.append(
            f"V_D verdict {contract.get('verdict')!r} != {case.expect_verdict!r}"
        )
    if case.expect_risk_state and payload.get("risk_state") != case.expect_risk_state:
        problems.append(
            f"risk_state {payload.get('risk_state')!r} != {case.expect_risk_state!r}"
        )
    if not problems:
        return []
    return [
        GapEntry(
            kind=GapKind.ENGINE_MOCK,
            claim=f"eval {case.case_id}: " + "; ".join(problems),
            notes="--eval writeback",
            evidence_id=f"eval:{case.case_id}",
        )
    ]


async def run_eval_case(case: EvalCase, project_root: Path) -> dict[str, Any]:
    set_tool_context(ToolContext(project_root=project_root, session_dir=None))
    try:
        raw = await engine_query(case.ticker, end=case.end)
        payload = json.loads(raw)
    except Exception as exc:  # noqa: BLE001 — eval must write back any failure
        payload = None
        error = f"{type(exc).__name__}: {exc}"
    else:
        error = None
    gaps = _failures_from_result(case, payload, error)
    if gaps:
        append_gaps(project_root, gaps, session_id="eval")
        refresh_profile_hints(
            project_root,
            extra_failures=[
                {
                    "id": f"eval:{case.case_id}",
                    "text": gaps[0].claim,
                    "capability": "engine_freshness",
                }
            ],
        )
    return {
        "case_id": case.case_id,
        "ok": not gaps,
        "payload": payload,
        "error": error,
        "gaps": [item.model_dump(mode="json") for item in gaps],
    }


async def run_eval(project_root: Path) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for case in CASES:
        results.append(await run_eval_case(case, project_root))
    return results


def run_eval_sync(project_root: Path) -> list[dict[str, Any]]:
    return asyncio.run(run_eval(project_root))
