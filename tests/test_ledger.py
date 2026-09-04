from __future__ import annotations

import json
from pathlib import Path

from momentum_research_agent.agents.audit import static_audit
from momentum_research_agent.agents.ledger import finalize_ledger, record_trace, replay_trace
from momentum_research_agent.models.schemas import (
    Evidence,
    EvidenceCategory,
    EvidenceStance,
    GapKind,
    ResearchReport,
    VerificationReport,
    VerificationStatus,
)
from momentum_research_agent.state.traces import append_traces, load_traces
from momentum_research_agent.tools.engine_adapter import normalize_engine_payload


def _report() -> ResearchReport:
    return ResearchReport(
        task_id="aa11bb22",
        title="Momentum state",
        agent_role="momentum_analyst",
        findings=[
            Evidence(
                id="ev01",
                claim="NVDA crowding is a crash signal.",
                category=EvidenceCategory.CROWDED_POSITIONING,
                stance=EvidenceStance.SUPPORTING,
                confidence="high",
                agent_id="aa11bb22",
            )
        ],
        summary="Crowded.",
        unanswered_questions=["Does FINRA SI confirm the crowding print?"],
        status="complete",
    )


def test_record_trace_ignores_non_engine_search() -> None:
    assert record_trace("market_data", {"ticker": "NVDA"}, "table") is None


def test_unchecked_and_mock_engine_become_gaps() -> None:
    report = _report()
    audit = static_audit("Is the NVDA selloff a crash?", [report])
    engine_obs = json.dumps(
        {
            "ticker": "NVDA",
            "source": "mock",
            "risk_state": "normal",
            "regime": "FRAGILITY_BUILDING",
            "note": "MOCK DATA",
        }
    )
    engine = record_trace(
        "engine_query",
        {"ticker": "NVDA", "end": "2026-05-29"},
        engine_obs,
        agent_id="aa11bb22",
        agent_role="momentum_analyst",
    )
    search = record_trace(
        "web_search",
        {"query": "NVDA momentum crash crowding May 2026"},
        "1. NVIDIA IR\n   https://nvidianews.nvidia.com/\n   Q1 FY2027 results",
        agent_id="aa11bb22",
        agent_role="momentum_analyst",
    )
    assert engine is not None
    assert search is not None
    ledger = finalize_ledger(audit, [report], [engine, search])
    kinds = {item.kind for item in ledger.gaps}
    assert GapKind.UNCHECKED_EVIDENCE in kinds
    assert GapKind.UNANSWERED_QUESTION in kinds
    assert GapKind.ENGINE_MOCK in kinds
    assert ledger.schema_kind == "momentum_gap_ledger"
    assert {item.id for item in ledger.traces} == {engine.id, search.id}
    crowding = next(item for item in ledger.gaps if item.kind is GapKind.UNCHECKED_EVIDENCE)
    assert engine.id in crowding.trace_ids
    assert search.id in crowding.trace_ids


def test_replay_search_uses_stored_observation() -> None:
    trace = record_trace(
        "web_search",
        {"query": "NVDA short interest"},
        "1. FINRA\n   https://www.finra.org/\n   SI print",
        agent_id="aa11bb22",
        agent_role="momentum_analyst",
    )
    assert trace is not None
    replayed = replay_trace(trace)
    assert replayed["ok"] is True
    assert replayed["method"] == "stored_observation"
    assert replayed["sha256_match"] is True
    assert "FINRA" in replayed["observation"]


def test_replay_engine_snapshot(tmp_path: Path) -> None:
    snap = tmp_path / "latest_assessment.json"
    raw = {
        "as_of_date": "2026-05-29",
        "overall_risk_state": "normal",
        "pm_posture": "escalate_for_pm_review",
        "mechanical_unwind_state": "FRAGILITY_BUILDING",
        "mechanism_scores": {"crowded_unwind": 96},
        "mechanism_statuses": {"crowded_theme_unwind": "triggered"},
        "theme_cluster": ["NVDA"],
    }
    snap.write_text(json.dumps(raw), encoding="utf-8")
    live = normalize_engine_payload(raw, "NVDA", snap, end="2026-05-29")
    trace = record_trace(
        "engine_query",
        {"ticker": "NVDA", "end": "2026-05-29"},
        json.dumps(live, indent=2),
        agent_id="aa11bb22",
        agent_role="momentum_analyst",
    )
    assert trace is not None
    assert trace.replay.method == "engine_snapshot"
    replayed = replay_trace(trace)
    assert replayed["ok"] is True
    assert replayed["sha256_match"] is True
    assert replayed["as_of"] == "2026-05-29"


def test_traces_jsonl_round_trip(tmp_path: Path) -> None:
    session = tmp_path / "session"
    session.mkdir()
    trace = record_trace(
        "web_search",
        {"query": "NVDA"},
        "snippet",
        agent_id="aa11bb22",
        agent_role="momentum_analyst",
    )
    assert trace is not None
    append_traces(session, [trace])
    loaded = load_traces(session)
    assert len(loaded) == 1
    assert loaded[0].id == trace.id
    assert loaded[0].observation_sha256 == trace.observation_sha256


def test_example_gap_ledger_validates() -> None:
    path = Path(__file__).resolve().parents[1] / "examples" / "nvda_momentum_gap_ledger.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    report = VerificationReport.model_validate(payload)
    assert report.schema_kind == "momentum_gap_ledger"
    assert report.traces[0].tool == "engine_query"
    assert report.traces[1].tool == "web_search"
    assert report.gaps[0].trace_ids
    replayed = replay_trace(report.traces[1])
    assert replayed["sha256_match"] is True
