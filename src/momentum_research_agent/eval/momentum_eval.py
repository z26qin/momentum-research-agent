"""Frozen US-equity momentum eval. Failures append to the gap ledger.

Cases cover Daniel–Moskowitz risk state, mechanical unwind, crowding, and
the engine delivery contract. No live DeepSeek calls.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from momentum_research_agent.config import find_project_root
from momentum_research_agent.coordinator.gap_seed import append_gaps
from momentum_research_agent.models.schemas import GapEntry, GapKind
from momentum_research_agent.tools.engine_adapter import (
    load_bundled_engine_state,
    normalize_engine_payload,
)
from momentum_research_agent.tools.engine_contract import attach_delivery_contract, grade_engine_payload
from momentum_research_agent.tools.engine_query import _mock_state, engine_query
from momentum_research_agent.tools.local_dm import geometric_closes, score_from_closes
from momentum_research_agent.tools.registry import ToolContext, set_tool_context

EVAL_SESSION_ID = "eval"


@dataclass(frozen=True)
class EvalCase:
    id: str
    ticker: str = "NVDA"
    end: str | None = "2026-05-29"
    snapshot: dict[str, Any] | None = None
    payload: dict[str, Any] | None = None
    expect_source: str | None = None
    expect_risk_state: str | None = None
    expect_regime: str | None = None
    expect_contract: str | None = None
    expect_as_of_match: bool | None = None
    mock: bool = False
    bundled: bool = False
    via_query: bool = False
    expect_pipeline_run: bool | None = None


@dataclass
class EvalResult:
    case_id: str
    passed: bool
    reasons: list[str] = field(default_factory=list)
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass
class EvalSummary:
    results: list[EvalResult]
    written: int = 0

    @property
    def failed(self) -> int:
        return sum(1 for item in self.results if not item.passed)

    @property
    def passed(self) -> int:
        return sum(1 for item in self.results if item.passed)


LATEST_ASSESSMENT = {
    "as_of_date": "2026-05-29",
    "overall_risk_state": "normal",
    "pm_posture": "escalate_for_pm_review",
    "mechanical_unwind_state": "FRAGILITY_BUILDING",
    "mechanism_scores": {"crowded_unwind": 96, "dm_recovery": 45},
    "mechanism_statuses": {
        "bear_market_recovery_crash": "watch",
        "crowded_theme_unwind": "triggered",
    },
    "score_is_probability": False,
    "theme_cluster": ["CIEN", "NVDA"],
}

CASES: tuple[EvalCase, ...] = (
    EvalCase(
        id="snapshot_normal_fragility",
        snapshot=LATEST_ASSESSMENT,
        expect_source="momentum-tail-risk-monitor",
        expect_risk_state="normal",
        expect_regime="FRAGILITY_BUILDING",
        expect_contract="pass_with_caveats",
        expect_as_of_match=True,
    ),
    EvalCase(
        id="stale_as_of_is_caveat",
        end="2026-08-01",
        snapshot=LATEST_ASSESSMENT,
        expect_source="momentum-tail-risk-monitor",
        expect_risk_state="normal",
        expect_contract="pass_with_caveats",
        expect_as_of_match=False,
    ),
    EvalCase(
        id="mock_engine_is_caveat",
        mock=True,
        expect_source="mock",
        expect_contract="pass_with_caveats",
    ),
    EvalCase(
        id="broken_payload_fails_vd",
        payload={"ticker": "NVDA", "source": "mock"},
        expect_contract="fail",
    ),
    EvalCase(
        id="unwind_panic_vocabulary",
        ticker="SMH",
        end="2026-06-30",
        snapshot={
            "temporal_scope": {"analysis_as_of_date": "2026-06-30"},
            "market_backdrop": {"dm_inspired_market_state": "panic_elevated"},
            "mechanical_unwind": {"unwind_state": "UNWIND"},
            "mechanism_scores": {"crowded_unwind": 80},
        },
        expect_source="momentum-tail-risk-monitor",
        expect_risk_state="panic_elevated",
        expect_regime="UNWIND",
        expect_contract="pass_with_caveats",
    ),
    EvalCase(
        id="local_dm_panic_unwind",
        payload=score_from_closes(
            "NVDA",
            geometric_closes(
                n=520,
                start=100.0,
                daily_mu=-0.001,
                shocks=(0.02, -0.02),
                end="2026-05-29",
                crash_days=21,
                crash_mu=-0.025,
            ),
            end="2026-05-29",
        )
        or {},
        expect_source="local_dm",
        expect_risk_state="panic_elevated",
        expect_regime="UNWIND",
        expect_contract="pass_with_caveats",
    ),
    EvalCase(
        id="pipeline_live_run",
        end="2026-05-29",
        payload={
            "ticker": "NVDA",
            "as_of": "2026-05-29",
            "source": "momentum-tail-risk-monitor",
            "risk_state": "normal",
            "regime": "FRAGILITY_BUILDING",
            "crowding_score": 0.96,
            "as_of_match": True,
            "pipeline_run": True,
        },
        expect_source="momentum-tail-risk-monitor",
        expect_risk_state="normal",
        expect_regime="FRAGILITY_BUILDING",
        expect_contract="pass",
    ),
    EvalCase(
        id="bundled_snapshot_2026_05_29",
        ticker="NVDA",
        end="2026-05-29",
        bundled=True,
        expect_source="momentum-tail-risk-monitor",
        expect_risk_state="normal",
        expect_regime="FRAGILITY_BUILDING",
        expect_contract="pass_with_caveats",
        expect_as_of_match=True,
    ),
    EvalCase(
        id="bundled_pipeline_replay",
        ticker="NVDA",
        end="2026-05-29",
        via_query=True,
        expect_source="momentum-tail-risk-monitor",
        expect_risk_state="normal",
        expect_regime="FRAGILITY_BUILDING",
        expect_contract="pass",
        expect_as_of_match=True,
        expect_pipeline_run=True,
    ),
    EvalCase(
        id="bundled_pipeline_replay_2026_06_30",
        ticker="SMH",
        end="2026-06-30",
        via_query=True,
        expect_source="momentum-tail-risk-monitor",
        expect_risk_state="normal",
        expect_regime="FRAGILITY_BUILDING",
        expect_contract="pass",
        expect_as_of_match=True,
        expect_pipeline_run=True,
    ),
)


def run_eval(project_root: Path, *, write_ledger: bool = True) -> EvalSummary:
    results = [_run_case(case, project_root=project_root) for case in CASES]
    written = 0
    if write_ledger:
        written = _append_failures(project_root, results)
        from momentum_research_agent.state.prompt_memory import refresh_profile_hints

        refresh_profile_hints(project_root)
    return EvalSummary(results=results, written=written)


def _engine_query_payload(
    ticker: str,
    end: str | None,
    *,
    project_root: Path | None = None,
) -> dict[str, Any]:
    from momentum_research_agent.tools.engine_pipeline import clear_pipeline_cache

    root = project_root or find_project_root()
    session_dir = root / "reports" / "eval"
    session_dir.mkdir(parents=True, exist_ok=True)
    set_tool_context(ToolContext(project_root=root, session_dir=session_dir))
    clear_pipeline_cache()
    raw = asyncio.run(engine_query(ticker, end=end))
    from momentum_research_agent.state.trajectory import append_tool_event

    append_tool_event(
        session_dir,
        agent="eval",
        tool="engine_query",
        arguments={"ticker": ticker, "end": end},
        result=raw,
        task_id="eval",
    )
    return json.loads(raw)


def _run_case(case: EvalCase, *, project_root: Path | None = None) -> EvalResult:
    if case.payload is not None:
        payload = attach_delivery_contract(case.payload, requested_end=case.end)
    elif case.mock:
        payload = attach_delivery_contract(
            _mock_state(
                case.ticker,
                None,
                case.end,
                reason="MOCK DATA — eval fixture",
            ),
            requested_end=case.end,
        )
    elif case.via_query:
        try:
            payload = _engine_query_payload(
                case.ticker, case.end, project_root=project_root
            )
        except Exception as exc:  # pragma: no cover - subprocess / context failures
            return EvalResult(
                case.id,
                passed=False,
                reasons=[f"engine_query error: {exc}"],
            )
    elif case.bundled:
        loaded = load_bundled_engine_state(case.ticker, end=case.end)
        if loaded is None:
            return EvalResult(
                case.id,
                passed=False,
                reasons=["bundled fixtures/engine snapshot missing"],
            )
        payload = attach_delivery_contract(loaded, requested_end=case.end)
    else:
        loaded = normalize_engine_payload(
            dict(case.snapshot or {}),
            case.ticker,
            Path(f"{case.id}.json"),
            end=case.end,
        )
        payload = attach_delivery_contract(loaded, requested_end=case.end)

    contract = payload.get("delivery_contract") or grade_engine_payload(
        payload, requested_end=case.end
    ).model_dump()
    reasons: list[str] = []
    if case.expect_source is not None and payload.get("source") != case.expect_source:
        reasons.append(f"source {payload.get('source')!r} != {case.expect_source!r}")
    if case.expect_risk_state is not None and payload.get("risk_state") != case.expect_risk_state:
        reasons.append(
            f"risk_state {payload.get('risk_state')!r} != {case.expect_risk_state!r}"
        )
    if case.expect_regime is not None and payload.get("regime") != case.expect_regime:
        reasons.append(f"regime {payload.get('regime')!r} != {case.expect_regime!r}")
    if (
        case.expect_as_of_match is not None
        and payload.get("as_of_match") is not case.expect_as_of_match
    ):
        reasons.append(
            f"as_of_match {payload.get('as_of_match')!r} != {case.expect_as_of_match!r}"
        )
    if (
        case.expect_pipeline_run is not None
        and payload.get("pipeline_run") is not case.expect_pipeline_run
    ):
        reasons.append(
            f"pipeline_run {payload.get('pipeline_run')!r} != {case.expect_pipeline_run!r}"
        )
    verdict = contract.get("verdict") if isinstance(contract, dict) else None
    if case.expect_contract is not None and verdict != case.expect_contract:
        reasons.append(f"V_D {verdict!r} != {case.expect_contract!r}")
    return EvalResult(case.id, passed=not reasons, reasons=reasons, payload=payload)


def _append_failures(project_root: Path, results: list[EvalResult]) -> int:
    failed = [item for item in results if not item.passed]
    if not failed:
        return 0
    gaps = [
        GapEntry(
            evidence_id=f"eval:{item.case_id}",
            claim=(
                f"engine snapshot / V_D eval {item.case_id} failed: "
                + "; ".join(item.reasons)
            ),
            kind=GapKind.UNCHECKED_EVIDENCE,
            notes="frozen engine/V_D eval",
        )
        for item in failed
    ]
    written = append_gaps(project_root, gaps, session_id=EVAL_SESSION_ID)
    return len(written)
