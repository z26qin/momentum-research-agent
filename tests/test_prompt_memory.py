from __future__ import annotations

from pathlib import Path

from momentum_research_agent.coordinator.gap_seed import append_gaps
from momentum_research_agent.models.schemas import GapEntry, GapKind, GapLedgerStatus
from momentum_research_agent.state.prompt_memory import (
    evolution_path,
    failure_brief,
    refresh_profile_hints,
)


def test_overlay_drops_closed_rules(tmp_path: Path) -> None:
    append_gaps(
        tmp_path,
        [
            GapEntry(
                kind=GapKind.ENGINE_MOCK,
                claim="engine_query(NVDA) mock on 2026-05-29",
                evidence_id="engine_mock:NVDA",
            )
        ],
        session_id="a",
    )
    refresh_profile_hints(tmp_path)
    text = (tmp_path / "reports" / "profile_hints.md").read_text(encoding="utf-8")
    assert "engine_mock:NVDA" in text
    assert "2026-05-29" in text
    assert failure_brief(tmp_path)
    evo = evolution_path(tmp_path)
    payload = evo.read_text(encoding="utf-8")
    assert "engine_mock:NVDA" in payload

    from momentum_research_agent.coordinator.gap_seed import load_rows, write_rows

    rows = load_rows(tmp_path)
    rows[0].status = GapLedgerStatus.CLOSED
    write_rows(tmp_path, rows)
    refresh_profile_hints(tmp_path)
    text = (tmp_path / "reports" / "profile_hints.md").read_text(encoding="utf-8")
    assert "engine_mock:NVDA" not in text
    assert "no open gap" in text
