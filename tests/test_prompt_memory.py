from __future__ import annotations

from pathlib import Path

from momentum_research_agent.coordinator.gap_seed import append_gaps
from momentum_research_agent.models.schemas import GapEntry, GapKind
from momentum_research_agent.state.prompt_memory import (
    decompose_user_message,
    load_profile_hints,
    refresh_profile_hints,
)
from momentum_research_agent.state.trajectory import append_tool_event


def test_decompose_message_includes_open_gaps(tmp_path: Path) -> None:
    append_gaps(
        tmp_path,
        [
            GapEntry(
                kind=GapKind.REJECTED_EVIDENCE,
                claim="crowding still elevated",
                evidence_id="e1",
                notes="no url",
            )
        ],
        session_id="prior-session",
    )
    message = decompose_user_message("Is this a crash?", tmp_path)
    assert "Research question:" in message
    assert "Is this a crash?" in message
    assert "Known gaps from prior sessions" in message
    assert "crowding still elevated" in message
    assert "Gap:" not in message.split("Research question:")[0]


def test_refresh_profile_hints_from_ledger_and_traces(tmp_path: Path) -> None:
    append_gaps(
        tmp_path,
        [
            GapEntry(
                kind=GapKind.UNCHECKED_EVIDENCE,
                claim="Daniel-Moskowitz unwind unchecked",
                evidence_id="e1",
            )
        ],
        session_id="sess-a",
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
    assert "learned" in evolution
    assert "engine_query(NVDA, end=unspecified)" in hints
    from json import loads

    payload = loads(evolution)
    assert any(item.get("source") == "trajectory" for item in payload["learned"])


def test_learned_rules_persist_and_drop_closed_gaps(tmp_path: Path) -> None:
    from momentum_research_agent.coordinator.gap_seed import load_rows, write_rows
    from momentum_research_agent.models.schemas import GapLedgerStatus
    from momentum_research_agent.state.persistence import load_json
    from momentum_research_agent.state.prompt_memory import evolution_path

    append_gaps(
        tmp_path,
        [
            GapEntry(
                kind=GapKind.UNCHECKED_EVIDENCE,
                claim="crowding still elevated in SMH",
                evidence_id="crowd-1",
            )
        ],
        session_id="sess-a",
    )
    prior = tmp_path / "reports" / "20260101_120000_deadbeef"
    prior.mkdir(parents=True)
    append_tool_event(
        prior,
        agent="momentum_analyst",
        tool="engine_query",
        arguments={"ticker": "NVDA", "end": "2026-08-01"},
        result='{"as_of_match": false, "note": "stale"}',
        task_id="abcd",
    )
    refresh_profile_hints(tmp_path)
    hints = load_profile_hints(tmp_path)
    assert "engine_query(NVDA, end=2026-08-01) had as_of_match=false" in hints
    assert "Open crowding gap crowd-1" in hints
    learned = load_json(evolution_path(tmp_path))["learned"]
    keys = {item["key"] for item in learned}
    assert "trace:stale_as_of:NVDA:2026-08-01" in keys
    assert "gap:crowd-1" in keys

    rows = load_rows(tmp_path)
    rows[0].status = GapLedgerStatus.CLOSED
    write_rows(tmp_path, rows)
    refresh_profile_hints(tmp_path)
    hints = load_profile_hints(tmp_path)
    assert "Open crowding gap crowd-1" not in hints
    assert "engine_query(NVDA, end=2026-08-01) had as_of_match=false" in hints


def test_load_profile_appends_hints(tmp_path: Path) -> None:
    from momentum_research_agent.agents.sub_agent import load_profile

    profiles = tmp_path / "profiles"
    profiles.mkdir()
    profiles.joinpath("momentum_analyst.md").write_text(
        "You are a momentum analyst.\n", encoding="utf-8"
    )
    refresh_root = tmp_path
    append_gaps(
        refresh_root,
        [
            GapEntry(
                kind=GapKind.REJECTED_EVIDENCE,
                claim="factor crowding in SMH",
                evidence_id="e1",
            )
        ],
        session_id="sess-a",
    )
    refresh_profile_hints(refresh_root)
    text = load_profile("momentum_analyst", tmp_path)
    assert "You are a momentum analyst." in text
    assert "factor crowding in SMH" in text
