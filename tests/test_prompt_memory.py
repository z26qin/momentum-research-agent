from __future__ import annotations

from pathlib import Path

from momentum_research_agent.models.schemas import (
    EvidenceVerdict,
    VerificationReport,
    VerificationStatus,
)
from momentum_research_agent.state.gap_ledger import append_from_verification, ledger_path
from momentum_research_agent.state.prompt_memory import (
    decompose_user_message,
    load_profile_hints,
    refresh_profile_hints,
)
from momentum_research_agent.state.trajectory import append_tool_event


def test_decompose_message_includes_open_gaps(tmp_path: Path) -> None:
    append_from_verification(
        ledger_path(tmp_path),
        VerificationReport(
            question="q",
            overall_status="fail",
            summary="prior",
            verdicts=[
                EvidenceVerdict(
                    evidence_id="e1",
                    claim="crowding still elevated",
                    status=VerificationStatus.REJECTED,
                    notes="no url",
                )
            ],
        ),
        "prior-session",
    )
    message = decompose_user_message("Is this a crash?", tmp_path)
    assert "Research question:" in message
    assert "Is this a crash?" in message
    assert "Known gaps from prior sessions" in message
    assert "crowding still elevated" in message
    assert "Gap:" not in message.split("Research question:")[0]


def test_refresh_profile_hints_from_ledger_and_traces(tmp_path: Path) -> None:
    append_from_verification(
        ledger_path(tmp_path),
        VerificationReport(
            question="q",
            overall_status="fail",
            summary="prior",
            verdicts=[
                EvidenceVerdict(
                    evidence_id="e1",
                    claim="Daniel-Moskowitz unwind unchecked",
                    status=VerificationStatus.UNCHECKED,
                )
            ],
        ),
        "sess-a",
    )
    prior = tmp_path / "reports" / "20260101_120000_deadbeef"
    prior.mkdir(parents=True)
    append_tool_event(
        prior,
        agent="momentum_analyst",
        tool="engine_query",
        arguments={"ticker": "NVDA"},
        result="MOCK DATA — no snapshot",
        task_id="abcd",
    )
    path = refresh_profile_hints(tmp_path)
    assert path is not None
    hints = load_profile_hints(tmp_path)
    assert "Runtime retrieval hints" in hints
    assert "unwind" in hints.lower()
    assert "mock_engine" in hints
    assert "Evolved retrieval rules" in hints
    evolution = (tmp_path / "reports" / "prompt_evolution.json").read_text(encoding="utf-8")
    assert "unwind_crash" in evolution
    assert "mock_engine" in evolution


def test_load_profile_appends_hints(tmp_path: Path) -> None:
    from momentum_research_agent.agents.sub_agent import load_profile

    profiles = tmp_path / "profiles"
    profiles.mkdir()
    profiles.joinpath("momentum_analyst.md").write_text(
        "You are a momentum analyst.\n", encoding="utf-8"
    )
    refresh_root = tmp_path
    append_from_verification(
        ledger_path(refresh_root),
        VerificationReport(
            question="q",
            overall_status="fail",
            summary="prior",
            verdicts=[
                EvidenceVerdict(
                    evidence_id="e1",
                    claim="factor crowding in SMH",
                    status=VerificationStatus.REJECTED,
                )
            ],
        ),
        "sess-a",
    )
    refresh_profile_hints(refresh_root)
    text = load_profile("momentum_analyst", tmp_path)
    assert "You are a momentum analyst." in text
    assert "factor crowding in SMH" in text
