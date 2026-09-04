"""Runtime prompt overlays from the gap ledger and prior trajectories.

Committed profile markdown stays frozen. This module writes a generated
hints file under reports/ and injects ledger/trace briefs into decompose.
That is system-level prompt evolution, not weight training.
"""

from __future__ import annotations

from pathlib import Path

from momentum_research_agent.config import reports_root
from momentum_research_agent.state.gap_ledger import failure_brief, ledger_path
from momentum_research_agent.state.persistence import save_text
from momentum_research_agent.state.trajectory import trajectory_failure_brief

HINTS_NAME = "profile_hints.md"


def hints_path(project_root: Path | None = None) -> Path:
    return reports_root(project_root) / HINTS_NAME


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
    return "\n\n".join(parts)


def load_profile_hints(project_root: Path | None = None) -> str:
    path = hints_path(project_root)
    if not path.is_file():
        return ""
    return path.read_text(encoding="utf-8").strip()


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
    if not brief and not traces:
        return None
    chunks = [
        "# Runtime retrieval hints",
        "",
        "Generated from the cross-session gap ledger and prior "
        "`trajectory.jsonl` files. They do not replace this analyst profile.",
        "",
        "Treat `engine_query` `source=mock` and `delivery_contract.verdict="
        "fail` as unlabeled. Prefer a live `momentum-tail-risk-monitor` "
        "snapshot. Crowding claims need FINRA/ETF/options sources; unwind/"
        "crash claims need Daniel–Moskowitz `risk_state` / `regime` fields.",
    ]
    if brief:
        chunks.extend(["", "## Open and recently consumed gaps", "", brief])
    if traces:
        chunks.extend(["", "## Recent tool-trace failures", "", traces])
    path = hints_path(project_root)
    save_text(path, "\n".join(chunks) + "\n")
    return path
