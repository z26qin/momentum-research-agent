"""Derived tool previews from traces.jsonl. Do not write a second log.

Overlay and replan read traces. This module is a truncated view for callers
that still want a preview dict.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from momentum_research_agent.state.traces import load_traces

PREVIEW_CHARS = 500


def load_trajectory(session_dir: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for trace in load_traces(session_dir):
        observation = trace.observation
        preview = (
            observation
            if len(observation) <= PREVIEW_CHARS
            else observation[:PREVIEW_CHARS] + "…"
        )
        rows.append(
            {
                "timestamp": trace.timestamp.isoformat(),
                "tool": trace.tool,
                "arguments": dict(trace.arguments),
                "preview": preview,
                "agent_id": trace.agent_id,
                "agent_role": trace.agent_role,
            }
        )
    return rows
