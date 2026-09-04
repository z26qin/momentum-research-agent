"""Runtime prompt overlays from the gap ledger and prior trajectories.

Committed profile markdown stays frozen. This module writes a generated
hints file under reports/ and injects ledger/trace briefs into decompose.
That is system-level prompt evolution, not weight training.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from momentum_research_agent.config import reports_root
from momentum_research_agent.models.schemas import GapCapability, GapState
from momentum_research_agent.state.gap_ledger import failure_brief, ledger_path, load_ledger
from momentum_research_agent.state.persistence import save_json, save_text
from momentum_research_agent.state.trajectory import (
    ENGINE_FAILURE_MARKERS,
    trajectory_failure_brief,
    trajectory_path,
)
from momentum_research_agent.state.trajectory import _failure_marker, _read_events

HINTS_NAME = "profile_hints.md"
EVOLUTION_NAME = "prompt_evolution.json"

_CAPABILITY_RULES: dict[GapCapability, str] = {
    GapCapability.CROWDING: (
        "Crowding claims need a retrieved FINRA SI / ETF flow / options source. "
        "Do not rest on engine crowding_score alone."
    ),
    GapCapability.UNWIND_CRASH: (
        "Unwind/crash claims need Daniel–Moskowitz `risk_state` / `regime` from "
        "engine_query plus V_D pass (or pass_with_caveats with the caveat named)."
    ),
    GapCapability.ENGINE_FRESHNESS: (
        "Prefer a live `scripts/run_monitor.py` PIT assessment over a stale JSON "
        "snapshot. source=mock and V_D fail are unlabeled."
    ),
    GapCapability.SOURCE_QUALITY: (
        "Every Evidence row needs a retrieved URL or engine source_path. "
        "Do not fabricate timestamps."
    ),
    GapCapability.OTHER: (
        "Stay inside US equity momentum factor risk (DM crash / crowding / unwind)."
    ),
}

_TRACE_RULES: dict[str, str] = {
    "mock_engine": (
        "Prior engine_query returned MOCK DATA. Call engine_query again with an "
        "as_of end date and require source=momentum-tail-risk-monitor."
    ),
    "vd_fail": (
        "Prior delivery_contract V_D was fail. Do not cite that payload; re-query "
        "until verdict is pass or pass_with_caveats."
    ),
    "stale_as_of": (
        "Prior snapshot as_of_match was false. Request a pipeline run for the "
        "requested end date instead of using the stale file."
    ),
    "no_snapshot": (
        "No monitor snapshot was found. Point MOMENTUM_ENGINE_DIR at the "
        "momentum-tail-risk-monitor checkout before claiming engine state."
    ),
}


def hints_path(project_root: Path | None = None) -> Path:
    return reports_root(project_root) / HINTS_NAME


def evolution_path(project_root: Path | None = None) -> Path:
    return reports_root(project_root) / EVOLUTION_NAME


def decompose_user_message(
    question: str,
    project_root: Path,
    session_dir: Path | None = None,
) -> str:
    parts = [f"Research question:\n\n{question}"]
    brief = failure_brief(ledger_path(project_root))
    if brief:
        parts.append(
            "Known gaps from prior sessions (do not invent tasks titled Gap:; "
            "the Coordinator seeds those separately from the ledger):\n"
            + brief
        )
    traces = trajectory_failure_brief(
        reports_root(project_root),
        exclude=session_dir,
    )
    if traces:
        parts.append(
            "Recent tool-trace failure patterns (bias retrieval toward live "
            "engine snapshots and sourced crowding/unwind evidence; do not add "
            "extra in-session loops):\n"
            + traces
        )
    rules = evolved_rules(project_root, session_dir)
    if rules:
        parts.append(
            "Evolved retrieval rules from prior gaps/traces (apply to this "
            "decomposition; do not add an extra in-session loop):\n"
            + "\n".join(f"- {item}" for item in rules)
        )
    return "\n\n".join(parts)


def load_profile_hints(project_root: Path | None = None) -> str:
    path = hints_path(project_root)
    if not path.is_file():
        return ""
    return path.read_text(encoding="utf-8").strip()


def evolved_rules(
    project_root: Path,
    session_dir: Path | None = None,
) -> list[str]:
    capabilities = _observed_capabilities(project_root)
    markers = _observed_markers(project_root, session_dir)
    rules: list[str] = []
    for cap in capabilities:
        text = _CAPABILITY_RULES.get(cap)
        if text:
            rules.append(text)
    for marker in markers:
        text = _TRACE_RULES.get(marker)
        if text:
            rules.append(text)
    return rules


def refresh_profile_hints(
    project_root: Path,
    session_dir: Path | None = None,
) -> Path | None:
    """Rewrite reports/profile_hints.md from current ledger + traces."""
    brief = failure_brief(ledger_path(project_root))
    traces = trajectory_failure_brief(
        reports_root(project_root),
        exclude=session_dir,
    )
    rules = evolved_rules(project_root, session_dir)
    if not brief and not traces and not rules:
        return None
    chunks = [
        "# Runtime retrieval hints",
        "",
        "Generated from the cross-session gap ledger and prior "
        "`trajectory.jsonl` files. They do not replace this analyst profile.",
        "",
        "Treat `engine_query` `source=mock` and `delivery_contract.verdict="
        "fail` as unlabeled. Prefer a live `scripts/run_monitor.py` PIT "
        "assessment. Crowding claims need FINRA/ETF/options sources; unwind/"
        "crash claims need Daniel–Moskowitz `risk_state` / `regime` fields.",
    ]
    if rules:
        chunks.extend(["", "## Evolved retrieval rules", ""])
        chunks.extend(f"- {item}" for item in rules)
    if brief:
        chunks.extend(["", "## Open and recently consumed gaps", "", brief])
    if traces:
        chunks.extend(["", "## Recent tool-trace failures", "", traces])
    path = hints_path(project_root)
    save_text(path, "\n".join(chunks) + "\n")
    save_json(
        evolution_path(project_root),
        {
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "capabilities": [item.value for item in _observed_capabilities(project_root)],
            "trace_markers": _observed_markers(project_root, session_dir),
            "rules": rules,
        },
    )
    return path


def _observed_capabilities(project_root: Path) -> list[GapCapability]:
    by_id = load_ledger(ledger_path(project_root))
    ordered: list[GapCapability] = []
    seen: set[GapCapability] = set()
    for record in by_id.values():
        if record.state is GapState.CONSUMED and record.capability in seen:
            continue
        if record.capability in seen:
            continue
        seen.add(record.capability)
        ordered.append(record.capability)
    return ordered


def _observed_markers(project_root: Path, session_dir: Path | None) -> list[str]:
    reports = reports_root(project_root)
    if not reports.is_dir():
        return []
    skip = session_dir.resolve() if session_dir is not None else None
    found: list[str] = []
    seen: set[str] = set()
    sessions = sorted(
        (
            path
            for path in reports.iterdir()
            if path.is_dir() and trajectory_path(path).is_file()
        ),
        key=lambda path: path.name,
        reverse=True,
    )
    for session in sessions[:3]:
        if skip is not None and session == skip:
            continue
        for raw in _read_events(trajectory_path(session)):
            marker = _failure_marker(raw)
            if marker is None or marker not in ENGINE_FAILURE_MARKERS or marker in seen:
                continue
            seen.add(marker)
            found.append(marker)
    return found
