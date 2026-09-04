"""Read momentum-tail-risk-monitor artifacts without importing that package.

The engine is a PIT parquet pipeline, not a ticker API. This adapter maps
existing JSON snapshots (latest_assessment, structured_snapshot, evidence
cards) into the engine_query contract. A live `scripts/run_monitor.py`
subprocess is preferred when the snapshot as_of does not match. Missing
files fall back to local_dm / mock. Do not import that package.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from momentum_research_agent.config import find_project_root

DM_PRIMARY_STATES = ("normal", "bear_low_volatility", "panic_elevated")
DM_BEAR_STATES = frozenset({"bear_low_volatility", "panic_elevated"})
MECHANICAL_UNWIND_REGIMES = ("QUIET", "FRAGILITY_BUILDING", "UNWIND")
_EMPTY = (None, "", [], {})


def looks_like_engine(path: Path | None) -> bool:
    if path is None or not path.is_dir():
        return False
    return (
        (path / "scripts" / "run_monitor.py").is_file()
        or (path / "outputs").is_dir()
        or (path / "data" / "processed").is_dir()
    )


def resolve_engine_root(project_root: Path | None = None) -> Path | None:
    """Return the engine repo root, or None to keep engine_query on mock data.

    `MOMENTUM_ENGINE_DIR` wins. If it is set but missing, do not silently
    fall back to a sibling checkout. Otherwise look for
    `../momentum-tail-risk-monitor` next to this project.
    """
    raw = os.environ.get("MOMENTUM_ENGINE_DIR", "").strip()
    if raw:
        path = Path(raw).expanduser()
        return path if looks_like_engine(path) else None
    snapshot = os.environ.get("MOMENTUM_ENGINE_SNAPSHOT", "").strip()
    if snapshot:
        file_path = Path(snapshot).expanduser()
        if file_path.is_file():
            parent = file_path.parent
            return parent if looks_like_engine(parent) or file_path.is_file() else None
        if looks_like_engine(file_path):
            return file_path
        return None
    root = Path(project_root) if project_root is not None else find_project_root()
    sibling = root.parent / "momentum-tail-risk-monitor"
    if looks_like_engine(sibling):
        return sibling
    return None


def iter_engine_artifacts(root: Path) -> list[Path]:
    found: list[Path] = []
    latest = root / "outputs" / "latest_assessment.json"
    if latest.is_file():
        found.append(latest)
    mvp = root / "outputs" / "mvp"
    if mvp.is_dir():
        found.extend(sorted(mvp.glob("risk_state_*.json"), reverse=True))
    outputs = root / "outputs"
    if outputs.is_dir():
        found.extend(sorted(outputs.glob("snapshot_*/structured_snapshot.json"), reverse=True))
    return found


def select_engine_artifact(
    root: Path,
    as_of: str | None = None,
) -> Path | None:
    explicit = os.environ.get("MOMENTUM_ENGINE_SNAPSHOT", "").strip()
    if explicit:
        path = Path(explicit).expanduser()
        if path.is_file():
            return path
    candidates = iter_engine_artifacts(root)
    if not candidates:
        return None
    if not as_of:
        return candidates[0]
    matches: list[Path] = []
    for path in candidates:
        payload = _read_json(path)
        if payload is None:
            continue
        observed = artifact_as_of(path, payload)
        if observed == as_of or as_of in path.name or as_of in str(path.parent.name):
            matches.append(path)
    return matches[0] if matches else candidates[0]


def artifact_as_of(path: Path, payload: dict[str, Any]) -> str | None:
    value = _get(payload, "as_of_date", "as_of")
    if value:
        return str(value)[:10]
    temporal = payload.get("temporal_scope")
    if isinstance(temporal, dict) and temporal.get("analysis_as_of_date"):
        return str(temporal["analysis_as_of_date"])[:10]
    config = payload.get("config")
    if isinstance(config, dict) and config.get("as_of_date"):
        return str(config["as_of_date"])[:10]
    parent = path.parent.name
    if parent.startswith("snapshot_"):
        return parent.removeprefix("snapshot_")
    return None


def load_engine_state(
    ticker: str,
    start: str | None = None,
    end: str | None = None,
    *,
    project_root: Path | None = None,
) -> dict[str, Any] | None:
    as_of = end
    explicit = os.environ.get("MOMENTUM_ENGINE_SNAPSHOT", "").strip()
    if explicit:
        path = Path(explicit).expanduser()
        if path.is_file():
            payload = _read_json(path)
            if payload is None:
                return None
            return normalize_engine_payload(payload, ticker, path, start=start, end=end)
    root = resolve_engine_root(project_root)
    if root is None:
        return None
    path = select_engine_artifact(root, as_of=as_of)
    if path is None:
        return None
    payload = _read_json(path)
    if payload is None:
        return None
    return normalize_engine_payload(payload, ticker, path, start=start, end=end)


def normalize_engine_payload(
    payload: dict[str, Any],
    ticker: str,
    path: Path,
    *,
    start: str | None = None,
    end: str | None = None,
    pipeline_run: bool = False,
) -> dict[str, Any]:
    symbol = ticker.upper()
    as_of = artifact_as_of(path, payload) or end
    requested = end
    dm_state = _dm_state(payload)
    regime = _regime(payload)
    crash_freq = _crash_frequency(payload, dm_state)
    crowding = _crowding_score(payload)
    mechanisms = _mechanism_statuses(payload)
    scores = _mechanism_scores(payload)
    mentions = _ticker_mentions(payload, symbol)
    stale = bool(requested and as_of and requested != as_of)
    if pipeline_run:
        note_parts = [
            "Live PIT assessment via momentum-tail-risk-monitor scripts/run_monitor.py.",
            "Engine state is market/book level, not a single-name forecast.",
        ]
    else:
        note_parts = [
            "File adapter over momentum-tail-risk-monitor outputs; this is not a live pipeline run.",
            "Engine state is market/book level, not a single-name forecast.",
        ]
    if stale:
        note_parts.append(
            f"Requested as_of={requested} was not an exact match; using snapshot as_of={as_of}."
        )
    if mentions:
        note_parts.append(f"{symbol} appears in snapshot names/evidence.")
    else:
        note_parts.append(
            f"No {symbol}-specific row; interpret risk_state as the book/market snapshot."
        )
    return {
        "ticker": symbol,
        "start": start,
        "end": end,
        "as_of": as_of,
        "source": "momentum-tail-risk-monitor",
        "source_path": str(path),
        "pipeline_run": pipeline_run,
        "scope": "market_or_book",
        "as_of_match": not stale,
        "risk_state": dm_state,
        "pm_posture": _get(payload, "pm_posture", "posture"),
        "regime": regime,
        "conditional_crash_frequency": crash_freq,
        "dm_bear_market_indicator": dm_state in DM_BEAR_STATES
        or str(mechanisms.get("bear_market_recovery_crash") or "") == "triggered",
        "crowding_score": crowding,
        "mechanism_statuses": mechanisms,
        "mechanism_scores": scores,
        "ticker_mentions": mentions,
        "note": " ".join(note_parts),
    }


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return raw if isinstance(raw, dict) else None


def _get(payload: dict[str, Any], *names: str) -> Any:
    for name in names:
        value = payload.get(name)
        if value not in _EMPTY:
            return value
    for nested_key in (
        "evidence_card",
        "card",
        "config",
        "market_backdrop",
        "mechanical_unwind",
        "structural_unwind",
        "pm_response",
        "pm_book_stress",
        "run",
        "temporal_scope",
        "retrieved_evidence_state",
    ):
        nested = payload.get(nested_key)
        if not isinstance(nested, dict):
            continue
        for name in names:
            value = nested.get(name)
            if value not in _EMPTY:
                return value
    return None


def _dm_state(payload: dict[str, Any]) -> str:
    value = _get(payload, "overall_risk_state", "dm_inspired_market_state")
    if isinstance(value, str) and value:
        return value
    nested = payload.get("market_backdrop")
    if isinstance(nested, dict):
        state = nested.get("dm_inspired_market_state")
        if isinstance(state, str) and state:
            return state
    return "unknown"


def _regime(payload: dict[str, Any]) -> str:
    value = _get(
        payload,
        "mechanical_unwind_state",
        "unwind_state",
        "scenario_classification",
    )
    if isinstance(value, str) and value:
        return value
    mechanical = payload.get("mechanical_unwind")
    if isinstance(mechanical, dict):
        unwind = mechanical.get("unwind_state")
        if isinstance(unwind, str) and unwind:
            return unwind
    structural = payload.get("structural_unwind")
    if isinstance(structural, dict):
        scenario = structural.get("scenario_classification")
        if isinstance(scenario, str) and scenario:
            return scenario
    return _dm_state(payload)


def _crash_frequency(payload: dict[str, Any], dm_state: str) -> float | None:
    direct = _get(payload, "tail_loss_probability", "tail_loss_frequency")
    if isinstance(direct, bool):
        direct = None
    if isinstance(direct, (int, float)):
        return round(float(direct), 4)
    card = payload.get("evidence_card")
    if isinstance(card, dict):
        nested = card.get("tail_loss_frequency")
        if isinstance(nested, (int, float)) and not isinstance(nested, bool):
            return round(float(nested), 4)
        provenance = card.get("provenance") if isinstance(card.get("provenance"), dict) else {}
        nested = provenance.get("tail_loss_frequency") if provenance else None
        if isinstance(nested, (int, float)) and not isinstance(nested, bool):
            return round(float(nested), 4)
    analogs = _get(payload, "historical_analogs")
    if isinstance(analogs, list):
        for analog in analogs:
            if not isinstance(analog, dict):
                continue
            if analog.get("state") == dm_state and isinstance(
                analog.get("tail_loss_frequency"), (int, float)
            ):
                return round(float(analog["tail_loss_frequency"]), 4)
    return None


def _crowding_score(payload: dict[str, Any]) -> float | None:
    scores = payload.get("mechanism_scores")
    if isinstance(scores, dict) and isinstance(scores.get("crowded_unwind"), (int, float)):
        return round(float(scores["crowded_unwind"]) / 100.0, 3)
    mechanical = payload.get("mechanical_unwind")
    if isinstance(mechanical, dict):
        pct = mechanical.get("factor_footprint_percentile")
        if isinstance(pct, (int, float)) and not isinstance(pct, bool):
            return round(float(pct), 3)
    return None


def _mechanism_statuses(payload: dict[str, Any]) -> dict[str, Any]:
    value = payload.get("mechanism_statuses")
    if isinstance(value, dict):
        return value
    structural = payload.get("structural_unwind")
    if isinstance(structural, dict) and isinstance(structural.get("mechanism_statuses"), dict):
        return structural["mechanism_statuses"]
    return {}


def _mechanism_scores(payload: dict[str, Any]) -> dict[str, Any]:
    value = payload.get("mechanism_scores")
    return value if isinstance(value, dict) else {}


def _ticker_mentions(payload: dict[str, Any], ticker: str) -> list[str]:
    needle = ticker.upper()
    hits: list[str] = []
    cluster = payload.get("theme_cluster")
    if isinstance(cluster, list) and any(str(item).upper() == needle for item in cluster):
        hits.append("theme_cluster")
    structural = payload.get("structural_unwind")
    if isinstance(structural, dict):
        proxy = structural.get("theme_proxy")
        if isinstance(proxy, dict):
            symbols = proxy.get("cluster_symbols")
            if isinstance(symbols, list) and any(str(item).upper() == needle for item in symbols):
                hits.append("cluster_symbols")
    evidence_items = payload.get("retrieved_evidence")
    if not isinstance(evidence_items, list):
        state = payload.get("retrieved_evidence_state")
        if isinstance(state, dict):
            evidence_items = state.get("items")
    if isinstance(evidence_items, list):
        for item in evidence_items:
            if not isinstance(item, dict):
                continue
            blob = " ".join(
                str(item.get(key) or "")
                for key in ("headline_or_summary", "source", "evidence_id")
            )
            if needle in blob.upper():
                hits.append(str(item.get("evidence_id") or item.get("headline_or_summary")))
    return hits
