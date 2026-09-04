from __future__ import annotations

from pathlib import Path

from momentum_research_agent.coordinator.task_board import TaskBoard
from momentum_research_agent.models.schemas import (
    Evidence,
    EvidenceCategory,
    EvidenceStance,
    ResearchReport,
    Task,
)
from momentum_research_agent.state.reports import (
    LEGACY_MARKDOWN_NOTE,
    json_path,
    load_research_report,
    markdown_path,
    persist_research_report,
)


def _report(task: Task) -> ResearchReport:
    return ResearchReport(
        task_id=task.id,
        title=task.title,
        agent_role=task.profile,
        findings=[
            Evidence(
                id="evdeadbeef",
                claim="Crowding is fading.",
                category=EvidenceCategory.CROWDED_POSITIONING,
                stance=EvidenceStance.SUPPORTING,
                source_url="https://example.com/flow",
                source_name="example",
                excerpt="SI declined week over week.",
                confidence="high",
                agent_id=task.id,
            )
        ],
        summary="Rotation, not a cascade.",
        unanswered_questions=["Is ETF flow confirming?"],
        contradictions=["Volume is light versus a classic unwind."],
        status="complete",
    )


def test_persist_writes_json_and_markdown(tmp_path: Path) -> None:
    session = tmp_path / "session"
    board = TaskBoard(session, question="q")
    task = board.add_task("Momentum", "Check crowding", "momentum_analyst")
    report = _report(task)

    persist_research_report(session, task, report)

    assert json_path(session, task).exists()
    assert markdown_path(session, task).exists()
    loaded = load_research_report(session, task)
    assert loaded is not None
    assert loaded.findings[0].claim == "Crowding is fading."
    assert loaded.findings[0].confidence == "high"
    assert loaded.contradictions == ["Volume is light versus a classic unwind."]
    assert loaded.unanswered_questions == ["Is ETF flow confirming?"]
    assert loaded.status == "complete"


def test_resume_reloads_structured_json(tmp_path: Path) -> None:
    session = tmp_path / "session"
    board = TaskBoard(session, question="q")
    task = board.add_task("Momentum", "Check crowding", "momentum_analyst")
    board.activate(task.id)
    persist_research_report(session, task, _report(task))
    board.complete(task.id, "Rotation, not a cascade.")

    reloaded_board = TaskBoard.load(session)
    restored_task = reloaded_board.get(task.id)
    loaded = load_research_report(session, restored_task)
    assert loaded is not None
    assert loaded.model_dump(exclude={"findings"}) == _report(task).model_dump(exclude={"findings"})
    assert loaded.findings[0].source_url == "https://example.com/flow"
    assert loaded.findings[0].stance is EvidenceStance.SUPPORTING


def test_legacy_markdown_fallback_is_low_confidence(tmp_path: Path) -> None:
    session = tmp_path / "session"
    board = TaskBoard(session, question="q")
    task = board.add_task("Credit", "CDS", "credit_analyst")
    md = session / "sub_reports" / f"{task.id}_{task.profile}.md"
    md.parent.mkdir(parents=True, exist_ok=True)
    md.write_text("# Old narrative\n\nSpreads were quiet.\n", encoding="utf-8")

    loaded = load_research_report(session, task)
    assert loaded is not None
    assert loaded.status == "partial"
    assert loaded.findings[0].confidence == "low"
    assert LEGACY_MARKDOWN_NOTE in loaded.unanswered_questions
    assert "Spreads were quiet" in loaded.summary
