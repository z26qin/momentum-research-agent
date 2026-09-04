"""Runtime prompt overlays from the gap ledger and prior trajectories.

Committed profile markdown stays frozen. This module writes a generated
hints file under reports/ and injects ledger/trace briefs into decompose.
That is system-level prompt evolution, not weight training.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from momentum_research_agent.config import reports_root
from momentum_research_agent.models.schemas import GapLedgerStatus, MomentumCapability
from momentum_research_agent.state.persistence import load_json, save_json, save_text
from momentum_research_agent.state.trajectory import (
    ENGINE_FAILURE_MARKERS,
    trajectory_failure_brief,
    trajectory_path,
)
from momentum_research_agent.state.trajectory import _failure_marker, _read_events

HINTS_NAME = "profile_hints.md"
EVOLUTION_NAME = "prompt_evolution.json"
MAX_LEARNED_RULES = 12
_SCAN_SESSIONS = 8
_CLAIM_CHARS = 140

_CAPABILITY_RULES: dict[MomentumCapability, str] = {
    MomentumCapability.CROWDING: (
        "Crowding claims need a retrieved FINRA SI / ETF flow / options source. "
        "Do not rest on engine crowding_score alone."
    ),
    MomentumCapability.UNWIND_CRASH: (
        "Unwind/crash claims need Daniel–Moskowitz `risk_state` / `regime` from "
        "engine_query plus V_D pass (or pass_with_caveats with the caveat named)."
    ),
    MomentumCapability.ENGINE_FRESHNESS: (
        "Prefer a live `scripts/run_monitor.py` PIT assessment over a stale JSON "
        "snapshot. source=mock and V_D fail are unlabeled."
    ),
    MomentumCapability.SOURCE_QUALITY: (
        "Every Evidence row needs a retrieved URL or engine source_path. "
        "Do not fabricate timestamps."
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
    "momentum-tail-risk-monitor checkout, or use the frozen cases under "
    "fixtures/engine, before claiming engine state."
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
    from momentum_research_agent.coordinator.gap_seed import failure_brief

    brief = failure_brief(project_root)
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
    seen: set[str] = set()
    for cap in capabilities:
        text = _CAPABILITY_RULES.get(cap)
        if text:
            rules.append(text)
            seen.add(text)
    for marker in markers:
        text = _TRACE_RULES.get(marker)
        if text and text not in seen:
            rules.append(text)
            seen.add(text)
    for item in merge_learned_rules(project_root, session_dir):
        text = str(item.get("rule") or "").strip()
        if text and text not in seen:
            rules.append(text)
            seen.add(text)
    return rules


def merge_learned_rules(
    project_root: Path,
    session_dir: Path | None = None,
) -> list[dict[str, str]]:
    """Accumulate ticker/date-specific rules from traces + open gaps.

    Prior `prompt_evolution.json` learned rows persist even after the
    originating session falls out of the brief window. CLOSED gaps drop.
    """
    previous = _load_learned(project_root)
    incoming = [
        *_learned_from_traces(project_root, session_dir),
        *_learned_from_gaps(project_root),
    ]
    by_key: dict[str, dict[str, str]] = {}
    for item in previous:
        key = str(item.get("key") or "")
        if key:
            by_key[key] = item
    for item in incoming:
        key = str(item.get("key") or "")
        if key:
            by_key[key] = item
    closed = _closed_evidence_ids(project_root)
    ordered: list[str] = []
    seen: set[str] = set()
    for item in [*reversed(incoming), *reversed(previous)]:
        key = str(item.get("key") or "")
        if not key or key in seen:
            continue
        if key.startswith("gap:") and key.removeprefix("gap:") in closed:
            continue
        seen.add(key)
        ordered.append(key)
    keep = list(reversed(ordered))[-MAX_LEARNED_RULES:]
    return [by_key[key] for key in keep if key in by_key]


def refresh_profile_hints(
    project_root: Path,
    session_dir: Path | None = None,
) -> Path | None:
    """Rewrite reports/profile_hints.md from current ledger + traces."""
    from momentum_research_agent.coordinator.gap_seed import failure_brief

    brief = failure_brief(project_root)
    traces = trajectory_failure_brief(
        reports_root(project_root),
        exclude=session_dir,
    )
    learned = merge_learned_rules(project_root, session_dir)
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
            "learned": learned,
        },
    )
    return path


def _observed_capabilities(project_root: Path) -> list[MomentumCapability]:
    from momentum_research_agent.coordinator.gap_seed import load_rows

    ordered: list[MomentumCapability] = []
    seen: set[MomentumCapability] = set()
    for record in load_rows(project_root):
        if record.status is GapLedgerStatus.CONSUMED and record.capability in seen:
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


def _load_learned(project_root: Path) -> list[dict[str, str]]:
    path = evolution_path(project_root)
    if not path.is_file():
        return []
    try:
        payload = load_json(path)
    except (OSError, ValueError):
        return []
    if not isinstance(payload, dict):
        return []
    rows = payload.get("learned")
    if not isinstance(rows, list):
        return []
    learned: list[dict[str, str]] = []
    for row in rows:
        if isinstance(row, dict) and row.get("key") and row.get("rule"):
            learned.append({str(key): str(value) for key, value in row.items()})
    return learned


def _closed_evidence_ids(project_root: Path) -> set[str]:
    from momentum_research_agent.coordinator.gap_seed import load_rows

    return {
        row.evidence_id
        for row in load_rows(project_root)
        if row.status is GapLedgerStatus.CLOSED
    }


def _iter_trace_sessions(project_root: Path, session_dir: Path | None) -> list[Path]:
    reports = reports_root(project_root)
    if not reports.is_dir():
        return []
    skip = session_dir.resolve() if session_dir is not None else None
    sessions = sorted(
        (
            path
            for path in reports.iterdir()
            if path.is_dir() and trajectory_path(path).is_file()
        ),
        key=lambda path: path.name,
        reverse=True,
    )
    return [path for path in sessions if skip is None or path.resolve() != skip]


def _learned_from_traces(
    project_root: Path,
    session_dir: Path | None,
) -> list[dict[str, str]]:
    minted: list[dict[str, str]] = []
    seen: set[str] = set()
    for session in _iter_trace_sessions(project_root, session_dir)[:_SCAN_SESSIONS]:
        for raw in _read_events(trajectory_path(session)):
            item = _mint_trace_rule(raw)
            if item is None or item["key"] in seen:
                continue
            seen.add(item["key"])
            minted.append(item)
    return minted


def _learned_from_gaps(project_root: Path) -> list[dict[str, str]]:
    from momentum_research_agent.coordinator.gap_seed import load_rows

    minted: list[dict[str, str]] = []
    for row in load_rows(project_root):
        if row.status is GapLedgerStatus.CLOSED:
            continue
        item = _mint_gap_rule(row.evidence_id, row.capability, row.claim)
        if item is not None:
            minted.append(item)
    return minted


def _mint_trace_rule(event: dict) -> dict[str, str] | None:
    marker = _failure_marker(event)
    if marker is None or marker not in ENGINE_FAILURE_MARKERS:
        return None
    args = event.get("arguments") if isinstance(event.get("arguments"), dict) else {}
    ticker = str(args.get("ticker") or "UNKNOWN").upper()
    raw_end = args.get("end")
    if isinstance(raw_end, str) and raw_end.strip():
        end = raw_end.strip()[:10]
    else:
        end = "unspecified"
    key = f"trace:{marker}:{ticker}:{end}"
    templates = {
        "mock_engine": (
            f"engine_query({ticker}, end={end}) returned MOCK DATA. "
            "Re-query with a live or frozen-replay run_monitor.py PIT assessment; "
            "do not cite mock labels."
        ),
        "vd_fail": (
            f"engine_query({ticker}, end={end}) failed delivery_contract V_D. "
            "Do not cite that payload; require verdict pass or named caveats."
        ),
        "stale_as_of": (
            f"engine_query({ticker}, end={end}) had as_of_match=false. "
            "Request a pipeline run for that end date, not a mismatched snapshot."
        ),
        "no_snapshot": (
            f"engine_query({ticker}, end={end}) found no snapshot. "
            "Use MOMENTUM_ENGINE_DIR or fixtures/engine frozen dates before claiming state."
        ),
    }
    text = templates.get(marker)
    if text is None:
        return None
    return {"key": key, "rule": text, "marker": marker, "source": "trajectory"}


def _mint_gap_rule(
    evidence_id: str,
    capability: MomentumCapability,
    claim: str,
) -> dict[str, str] | None:
    if not evidence_id:
        return None
    clipped = " ".join(claim.split())
    if len(clipped) > _CLAIM_CHARS:
        clipped = clipped[: _CLAIM_CHARS - 3] + "..."
    return {
        "key": f"gap:{evidence_id}",
        "rule": (
            f"Open {capability.value} gap {evidence_id}: {clipped}. "
            "Retrieve a sourced observation (URL or engine source_path) before restating it."
        ),
        "marker": capability.value,
        "source": "gap_ledger",
    }
