from __future__ import annotations

import json
from pathlib import Path

from momentum_research_agent.state.trajectory import (
    append_tool_event,
    trajectory_failure_brief,
    trajectory_path,
)


def test_append_tool_event_jsonl(tmp_path: Path) -> None:
    append_tool_event(
        tmp_path,
        agent="momentum_analyst",
        tool="engine_query",
        arguments={"ticker": "NVDA"},
        result="ok",
        task_id="abcd",
    )
    path = trajectory_path(tmp_path)
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert rows[0]["tool"] == "engine_query"
    assert rows[0]["arguments"]["ticker"] == "NVDA"
    assert rows[0]["task_id"] == "abcd"
    assert rows[0]["result_chars"] == 2


def test_trajectory_failure_brief_flags_mock(tmp_path: Path) -> None:
    session = tmp_path / "20260101_120000_abcd1234"
    session.mkdir()
    append_tool_event(
        session,
        agent="momentum_analyst",
        tool="engine_query",
        arguments={"ticker": "NVDA"},
        result="MOCK DATA — no momentum-tail-risk-monitor snapshot found.",
        task_id="abcd",
    )
    brief = trajectory_failure_brief(tmp_path)
    assert "mock_engine" in brief
    assert "engine_query" in brief
