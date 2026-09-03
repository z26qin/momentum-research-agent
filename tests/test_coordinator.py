from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from momentum_research_agent.coordinator.coordinator import Coordinator
from momentum_research_agent.models.schemas import SubReport, UsageSummary


class FakeUsage:
    prompt_tokens = 100
    completion_tokens = 50


class FakeResponse:
    def __init__(self, content: str) -> None:
        self.choices = [SimpleNamespace(message=SimpleNamespace(content=content, tool_calls=None))]
        self.usage = FakeUsage()


class FakeCompletions:
    def __init__(self, payloads: list[str]) -> None:
        self._payloads = list(payloads)
        self.calls: list[dict] = []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        if not self._payloads:
            raise AssertionError("unexpected extra LLM call")
        return FakeResponse(self._payloads.pop(0))


class FakeClient:
    def __init__(self, payloads: list[str]) -> None:
        self.completions = FakeCompletions(payloads)
        self.chat = SimpleNamespace(completions=self.completions)


DECOMPOSE = json.dumps(
    {
        "reasoning": "Split price-factor state from credit confirmation.",
        "tasks": [
            {
                "title": "Momentum state",
                "assignment": "Query the engine and tape for NVDA momentum crash risk.",
                "profile": "momentum_analyst",
            },
            {
                "title": "Credit overlay",
                "assignment": "Check whether NVDA credit confirms the equity unwind.",
                "profile": "credit_analyst",
            },
        ],
    }
)

SYNTHESIS = json.dumps(
    {
        "question": "Is the NVDA selloff a crash?",
        "executive_summary": "The tape looks like a rotation, not a DM crash.",
        "analysis_by_dimension": {
            "momentum": "Crowding is fading but crash frequency is not critical.",
            "credit": "No credit event confirms an unwind cascade.",
        },
        "risk_assessment": "Net read is healthy rotation with residual crowding risk.",
        "actionable_signals": ["Do not flatten the whole book", "Watch SMH breadth"],
        "confidence_level": "medium",
        "dissenting_views": ["Credit data is thin"],
    }
)


@pytest.mark.asyncio
async def test_decompose_dispatch_synthesize_writes_artifacts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    session_dir = tmp_path / "20260101_120000_deadbeef"
    client = FakeClient([DECOMPOSE, SYNTHESIS])
    usage = UsageSummary()
    coordinator = Coordinator(
        session_dir=session_dir,
        client=client,  # type: ignore[arg-type]
        question="Is the NVDA selloff a crash?",
        project_root=tmp_path,
        sub_model="deepseek-chat",
        coordinator_model_name="deepseek-reasoner",
        max_sub_agents=4,
        usage_tracker=usage,
    )

    async def fake_run(self, task, tools, session_dir):
        report = SubReport(
            task_id=task.id,
            title=task.title,
            findings=f"Mock findings for {task.profile}",
            confidence="high",
            key_data_points=["mock"],
            risks_flagged=[],
            sources=["test"],
        )
        out = Path(session_dir) / "sub_reports" / f"{task.id}_{task.profile}.md"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(report.findings, encoding="utf-8")
        return report

    monkeypatch.setattr(
        "momentum_research_agent.coordinator.coordinator.SubAgent.run",
        fake_run,
    )

    report = await coordinator.run("Is the NVDA selloff a crash?")

    assert report.executive_summary.startswith("The tape looks like a rotation")
    assert (session_dir / "task_board.json").exists()
    assert (session_dir / "synthesis.md").exists()
    assert (session_dir / "synthesis.json").exists()
    written = list((session_dir / "sub_reports").glob("*.md"))
    assert len(written) == 2
    board = json.loads((session_dir / "task_board.json").read_text(encoding="utf-8"))
    assert board["question"] == "Is the NVDA selloff a crash?"
    assert {task["status"] for task in board["tasks"]} == {"COMPLETED"}
    assert len(client.completions.calls) == 2
    assert usage.total_tokens == 300
    synthesis_text = (session_dir / "synthesis.md").read_text(encoding="utf-8")
    assert "Actionable Signals" in synthesis_text
