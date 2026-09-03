"""Coordinator: decompose → dispatch in parallel → synthesize a PM brief."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from openai import AsyncOpenAI
from pydantic import ValidationError
from rich.console import Console
from rich.live import Live
from rich.table import Table

from momentum_research_agent.agents.sub_agent import SubAgent, render_sub_report_markdown
from momentum_research_agent.config import coordinator_model, sub_agent_model, usage_cost_usd
from momentum_research_agent.coordinator.task_board import TaskBoard
from momentum_research_agent.models.schemas import (
    DecompositionResult,
    SubReport,
    SynthesisReport,
    Task,
    TaskStatus,
    UsageSummary,
    parse_model_json,
    utcnow,
)
from momentum_research_agent.state.persistence import save_text
from momentum_research_agent.tools import DEFAULT_TOOLS, PROFILE_TOOLS

PROMPTS_DIR = Path(__file__).parent / "prompts"


class Coordinator:
    def __init__(
        self,
        session_dir: Path,
        client: AsyncOpenAI,
        question: str = "",
        project_root: Path | None = None,
        board: TaskBoard | None = None,
        sub_model: str | None = None,
        coordinator_model_name: str | None = None,
        max_sub_agents: int = 4,
        verbose: bool = False,
        console: Console | None = None,
        usage_tracker: UsageSummary | None = None,
        max_turns: int = 15,
    ) -> None:
        self.session_dir = Path(session_dir)
        self.session_dir.mkdir(parents=True, exist_ok=True)
        (self.session_dir / "sub_reports").mkdir(exist_ok=True)
        self.client = client
        self.project_root = Path(project_root) if project_root else Path.cwd()
        self.board = board or TaskBoard(self.session_dir, question=question)
        if question and not self.board.question:
            self.board.question = question
        self.sub_model = sub_model or sub_agent_model()
        self.coordinator_model_name = coordinator_model_name or coordinator_model()
        self.max_sub_agents = max_sub_agents
        self.verbose = verbose
        self.console = console or Console()
        self.usage_tracker = usage_tracker or UsageSummary()
        self.max_turns = max_turns
        self.sub_reports: dict[str, SubReport] = {}

    async def run(self, question: str) -> SynthesisReport:
        self.board.question = question
        self.board.save()
        await self.decompose(question)
        await self.dispatch_all()
        return await self.synthesize()

    async def resume(self) -> SynthesisReport:
        synthesis_path = self.session_dir / "synthesis.md"
        pending = [
            task
            for task in self.board.tasks
            if task.status in {TaskStatus.PENDING, TaskStatus.BLOCKED, TaskStatus.ACTIVE}
        ]
        if pending:
            self.board.requeue_unfinished()
            await self.dispatch_all()
        elif not self.board.tasks:
            await self.decompose(self.board.question)
            await self.dispatch_all()
        self._load_existing_sub_reports()
        json_path = self.session_dir / "synthesis.json"
        if json_path.exists() and not pending:
            return SynthesisReport.model_validate_json(json_path.read_text(encoding="utf-8"))
        if synthesis_path.exists() and not pending:
            return parse_model_json(SynthesisReport, synthesis_path.read_text(encoding="utf-8"))
        return await self.synthesize()

    async def decompose(self, question: str) -> list[Task]:
        system_prompt = (PROMPTS_DIR / "decompose.md").read_text(encoding="utf-8")
        user_message = f"Research question:\n\n{question}"
        result = await self._complete_json(
            system_prompt,
            user_message,
            DecompositionResult,
            self.coordinator_model_name,
        )
        created: list[Task] = []
        for spec in result.tasks[: self.max_sub_agents]:
            created.append(
                self.board.add_task(
                    title=spec.title,
                    assignment=spec.assignment,
                    profile=spec.profile,
                )
            )
        self.console.print(f"[bold]Decomposition[/bold] — {result.reasoning}\n")
        self.console.print(self.render_board_table())
        return created

    async def dispatch_all(self) -> None:
        pending = self.board.pending
        if not pending:
            return

        semaphore = asyncio.Semaphore(self.max_sub_agents)

        async def run_one(task: Task) -> SubReport | Exception:
            async with semaphore:
                self.board.activate(task.id)
                agent = SubAgent(
                    client=self.client,
                    model=self.sub_model,
                    project_root=self.project_root,
                    usage_tracker=self.usage_tracker,
                    max_turns=self.max_turns,
                    verbose=self.verbose,
                    on_progress=self._on_progress,
                    console=self.console,
                )
                tools = PROFILE_TOOLS.get(task.profile, DEFAULT_TOOLS)
                return await agent.run(task, tools, self.session_dir)

        with Live(self.render_board_table(), console=self.console, refresh_per_second=4) as live:
            gathered = await asyncio.gather(
                *[self._tracked(run_one, task, live) for task in pending],
                return_exceptions=True,
            )

        for task, result in zip(pending, gathered, strict=False):
            if isinstance(result, Exception):
                self.console.print(f"[red]Task {task.id} failed:[/red] {result}")
                self.board.fail(task.id, str(result))
                continue
            assert isinstance(result, SubReport)
            self.sub_reports[task.id] = result
            self.board.complete(task.id, result.findings)

        self.console.print(self.render_board_table())

    async def synthesize(self) -> SynthesisReport:
        self._load_existing_sub_reports()
        system_prompt = (PROMPTS_DIR / "synthesize.md").read_text(encoding="utf-8")
        missing = [
            task
            for task in self.board.tasks
            if task.status in {TaskStatus.BLOCKED, TaskStatus.CANCELLED}
        ]
        completed = [
            task for task in self.board.tasks if task.status == TaskStatus.COMPLETED
        ]
        chunks: list[str] = [f"Original research question:\n{self.board.question}\n"]
        for task in completed:
            report = self.sub_reports.get(task.id)
            body = render_sub_report_markdown(report) if report else (task.report or "")
            chunks.append(f"## Sub-report: {task.title} [{task.profile}]\n\n{body}")
        if missing:
            names = ", ".join(f"{task.title} ({task.status.value}: {task.error})" for task in missing)
            chunks.append(
                "The following dimensions are missing because the sub-agent failed "
                f"or was cancelled: {names}. Note the gap in the synthesis."
            )
        raw = await self._complete_json(
            system_prompt,
            "\n\n---\n\n".join(chunks),
            SynthesisReport,
            self.coordinator_model_name,
        )
        report = raw.model_copy(update={"question": self.board.question, "timestamp": utcnow()})
        save_text(self.session_dir / "synthesis.md", _render_synthesis_markdown(report))
        save_text(
            self.session_dir / "synthesis.json",
            report.model_dump_json(indent=2),
        )
        return report

    def render_board_table(self) -> Table:
        table = Table(title=f"Task board · {self.board.summary}", expand=True)
        table.add_column("ID", style="cyan", no_wrap=True)
        table.add_column("Title")
        table.add_column("Profile")
        table.add_column("Status")
        table.add_column("Tools", justify="right")
        table.add_column("Tokens", justify="right")
        style = {
            TaskStatus.PENDING: "dim",
            TaskStatus.ACTIVE: "yellow",
            TaskStatus.COMPLETED: "green",
            TaskStatus.BLOCKED: "red",
            TaskStatus.CANCELLED: "magenta",
        }
        for task in self.board.tasks:
            table.add_row(
                task.id,
                task.title,
                task.profile,
                f"[{style[task.status]}]{task.status.value}[/]",
                str(task.tool_calls),
                str(task.tokens_used),
            )
        return table

    def cost_summary_lines(self) -> list[str]:
        lines = ["Token / cost summary"]
        for model, bucket in self.usage_tracker.totals().items():
            cost = usage_cost_usd(
                UsageSummary.model_validate(
                    {
                        "events": [
                            {
                                "model": model,
                                "prompt_tokens": bucket["prompt_tokens"],
                                "completion_tokens": bucket["completion_tokens"],
                            }
                        ]
                    }
                )
            )
            lines.append(
                f"  {model}: {bucket['calls']} calls · "
                f"in={bucket['prompt_tokens']:,} out={bucket['completion_tokens']:,} · "
                f"${cost:.4f}"
            )
        lines.append(
            f"  total tokens={self.usage_tracker.total_tokens:,} · "
            f"${usage_cost_usd(self.usage_tracker):.4f}"
        )
        return lines

    async def _complete_json(
        self,
        system_prompt: str,
        user_message: str,
        model_cls: type,
        model: str,
    ) -> Any:
        messages: list[dict[str, str]] = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ]
        last_error = ""
        for _attempt in range(2):
            if last_error:
                messages.append(
                    {
                        "role": "user",
                        "content": (
                            "Your previous response failed schema validation:\n"
                            f"{last_error}\n\n"
                            "Return ONLY valid JSON matching the requested schema."
                        ),
                    }
                )
            response = await self.client.chat.completions.create(
                model=model,
                messages=messages,
                response_format={"type": "json_object"},
            )
            usage = getattr(response, "usage", None)
            if usage is not None:
                self.usage_tracker.add(
                    model,
                    int(getattr(usage, "prompt_tokens", 0) or 0),
                    int(getattr(usage, "completion_tokens", 0) or 0),
                )
            content = response.choices[0].message.content or ""
            try:
                return parse_model_json(model_cls, content)
            except ValidationError as exc:
                last_error = str(exc)
                messages.append({"role": "assistant", "content": content})
        raise ValueError(f"Could not parse {model_cls.__name__} after retry: {last_error}")

    def _on_progress(self, task_id: str, tool_calls: int, tokens_used: int) -> None:
        try:
            self.board.record_usage(task_id, tool_calls=tool_calls, tokens_used=tokens_used)
        except KeyError:
            return

    async def _tracked(self, fn, task: Task, live: Live):
        try:
            return await fn(task)
        finally:
            live.update(self.render_board_table())

    def _load_existing_sub_reports(self) -> None:
        folder = self.session_dir / "sub_reports"
        if not folder.exists():
            return
        for task in self.board.completed:
            if task.id in self.sub_reports:
                continue
            matches = list(folder.glob(f"{task.id}_*.md"))
            if not matches:
                continue
            text = matches[0].read_text(encoding="utf-8")
            self.sub_reports[task.id] = SubReport(
                task_id=task.id,
                title=task.title,
                findings=text,
                confidence="medium",
            )


def _render_synthesis_markdown(report: SynthesisReport) -> str:
    dimensions = "\n\n".join(
        f"### {name}\n\n{body}" for name, body in report.analysis_by_dimension.items()
    ) or "_(none)_"
    signals = "\n".join(f"- {item}" for item in report.actionable_signals) or "- (none)"
    dissent = "\n".join(f"- {item}" for item in report.dissenting_views) or "- (none)"
    return (
        f"# Synthesis\n\n"
        f"**Question:** {report.question}\n\n"
        f"**Timestamp:** {report.timestamp.isoformat()}\n\n"
        f"**Confidence:** {report.confidence_level}\n\n"
        f"## Executive Summary\n\n{report.executive_summary}\n\n"
        f"## Analysis by Dimension\n\n{dimensions}\n\n"
        f"## Cross-Dimensional Risk Assessment\n\n{report.risk_assessment}\n\n"
        f"## Actionable Signals\n\n{signals}\n\n"
        f"## Dissenting Views\n\n{dissent}\n"
    )
