"""Runtime prompt overlay from OPEN gaps and trajectory failure markers.

Does not import coordinator.gap_seed (circular). Committed profiles stay frozen.
CLOSED ledger rows drop their rules.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from momentum_research_agent.config import reports_root

TICKER_RE = re.compile(r"\b([A-Z]{1,5})\b")
DATE_RE = re.compile(r"\b(20\d{2}-\d{2}-\d{2})\b")


def evolution_path(project_root: Path) -> Path:
    return reports_root(project_root) / "prompt_evolution.json"


def hints_path(project_root: Path) -> Path:
    return reports_root(project_root) / "profile_hints.md"


def _ledger_path(project_root: Path) -> Path:
    return reports_root(project_root) / "gap_ledger.jsonl"


def _load_ledger_rows(project_root: Path) -> list[dict[str, Any]]:
    path = _ledger_path(project_root)
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        rows.append(json.loads(line))
    return rows


def _rule_from_text(rule_id: str, text: str, capability: str | None = None) -> dict[str, Any]:
    tickers = TICKER_RE.findall(text.upper())
    dates = DATE_RE.findall(text)
    ticker = next((item for item in tickers if item not in {"OPEN", "CLOSED", "MOCK", "FINRA"}), None)
    return {
        "id": rule_id,
        "ticker": ticker,
        "as_of": dates[0] if dates else None,
        "capability": capability,
        "text": text.strip()[:300],
    }


def refresh_profile_hints(
    project_root: Path,
    *,
    extra_failures: list[dict[str, Any]] | None = None,
) -> Path:
    """Rewrite overlay from OPEN gaps plus optional eval/trajectory failure markers."""
    rows = _load_ledger_rows(project_root)
    closed_ids = {
        str(row.get("evidence_id"))
        for row in rows
        if str(row.get("status") or "") == "CLOSED" and row.get("evidence_id")
    }
    rules: dict[str, dict[str, Any]] = {}
    for row in rows:
        status = str(row.get("status") or "")
        key = str(row.get("evidence_id") or "")
        if not key or status == "CLOSED":
            continue
        if status not in {"OPEN", "CONSUMED"}:
            continue
        claim = str(row.get("claim") or "")
        cap = str(row.get("capability") or "")
        rules[key] = _rule_from_text(key, claim, cap or None)
    for item in extra_failures or []:
        key = str(item.get("id") or item.get("evidence_id") or "")
        if not key or key in closed_ids:
            continue
        rules[key] = _rule_from_text(
            key,
            str(item.get("text") or item.get("claim") or key),
            str(item.get("capability") or "") or None,
        )
    for key in list(rules):
        if key in closed_ids:
            del rules[key]
    ordered = list(rules.values())
    payload = {"schema": "prompt_evolution_v1", "rules": ordered}
    evo = evolution_path(project_root)
    evo.parent.mkdir(parents=True, exist_ok=True)
    evo.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    lines = [
        "# Runtime profile hints (generated; do not commit analyst profiles)",
        "",
        "Apply these capability rules in addition to your frozen profile.",
        "",
    ]
    if not ordered:
        lines.append("(no open gap or failure rules)")
    for rule in ordered:
        loc = " ".join(
            part
            for part in (
                f"ticker={rule['ticker']}" if rule.get("ticker") else "",
                f"as_of={rule['as_of']}" if rule.get("as_of") else "",
                f"capability={rule['capability']}" if rule.get("capability") else "",
            )
            if part
        )
        lines.append(f"- `{rule['id']}` {loc}: {rule['text']}")
    hints = hints_path(project_root)
    hints.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return hints


def overlay_text(project_root: Path) -> str:
    path = hints_path(project_root)
    if not path.is_file():
        return ""
    return path.read_text(encoding="utf-8").strip()


def failure_brief(project_root: Path) -> str:
    """Short OPEN-gap brief for decompose. Reads jsonl directly."""
    open_rows = [
        row
        for row in _load_ledger_rows(project_root)
        if str(row.get("status") or "") == "OPEN"
    ]
    if not open_rows:
        return ""
    lines = ["Prior-session OPEN gaps (not a second follow-up):"]
    for row in open_rows[:6]:
        lines.append(
            f"- {row.get('capability')}: {row.get('claim')} "
            f"(evidence_id={row.get('evidence_id')})"
        )
    return "\n".join(lines)
