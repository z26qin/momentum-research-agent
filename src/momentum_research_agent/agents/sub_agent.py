"""Profile-bound ReAct runner that writes a SubReport to the session directory."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Optional

from openai import AsyncOpenAI
from pydantic import ValidationError

from momentum_research_agent.agents.react_loop import react_loop
from momentum_research_agent.models.schemas import SubReport, Task, UsageSummary, parse_model_json
from momentum_research_agent.state.persistence import save_text
from momentum_research_agent.tools import DEFAULT_TOOLS, PROFILE_TOOLS
from momentum_research_agent.tools.registry import (
    ToolContext,
    resolve_tools,
    set_tool_context,
)

OnProgress = Callable[[str, int, int], None]


def load_profile(profile: str, project_root: Path) -> str:
    name = profile.removesuffix(".md")
    candidates = [
        project_root / "profiles" / f"{name}.md",
        Path(__file__).parent / "profiles" / f"{name}.md",
    ]
    for path in candidates:
        if path.exists():
            return path.read_text(encoding="utf-8")
    known = ", ".join(p.stem for p in (Path(__file__).parent / "profiles").glob("*.md"))
    raise FileNotFoundError(f"Unknown profile '{profile}'. Available: {known}")


def _report_instructions(task: Task) -> str:
    return (
        f"# Assignment\n\n{task.assignment}\n\n"
        "Investigate using your tools. When you have enough evidence, stop calling tools "
        "and respond with a JSON object matching this schema (no markdown fences):\n"
        "{\n"
        f'  "task_id": "{task.id}",\n'
        f'  "title": "{task.title}",\n'
        '  "findings": "markdown analysis body",\n'
        '  "confidence": "high" | "medium" | "low",\n'
        '  "key_data_points": ["..."],\n'
        '  "risks_flagged": ["..."],\n'
        '  "sources": ["..."]\n'
        "}\n"
        "Be precise with numbers. Flag speculation explicitly. State a clear view."
    )


def _fallback_report(task: Task, text: str, error: str | None = None) -> SubReport:
    findings = text.strip() if text.strip() else (error or "Sub-agent produced no report.")
    if error:
        findings = f"{findings}\n\n_Error: {error}_"
    return SubReport(
        task_id=task.id,
        title=task.title,
        findings=findings,
        confidence="low",
        key_data_points=[],
        risks_flagged=[error] if error else [],
        sources=[],
    )


def render_sub_report_markdown(report: SubReport) -> str:
    points = "\n".join(f"- {item}" for item in report.key_data_points) or "- (none)"
    risks = "\n".join(f"- {item}" for item in report.risks_flagged) or "- (none)"
    sources = "\n".join(f"- {item}" for item in report.sources) or "- (none)"
    return (
        f"# {report.title}\n\n"
        f"- Task ID: `{report.task_id}`\n"
        f"- Confidence: **{report.confidence}**\n\n"
        f"## Findings\n\n{report.findings}\n\n"
        f"## Key Data Points\n\n{points}\n\n"
        f"## Risks Flagged\n\n{risks}\n\n"
        f"## Sources\n\n{sources}\n"
    )


class SubAgent:
    def __init__(
        self,
        client: AsyncOpenAI,
        model: str,
        project_root: Path,
        usage_tracker: UsageSummary | None = None,
        max_turns: int = 15,
        verbose: bool = False,
        on_progress: Optional[OnProgress] = None,
        console=None,
    ) -> None:
        self.client = client
        self.model = model
        self.project_root = Path(project_root)
        self.usage_tracker = usage_tracker
        self.max_turns = max_turns
        self.verbose = verbose
        self.on_progress = on_progress
        self.console = console

    async def run(
        self,
        task: Task,
        tools: list[str],
        session_dir: Path,
    ) -> SubReport:
        session_dir = Path(session_dir)
        tool_names = tools or PROFILE_TOOLS.get(task.profile, DEFAULT_TOOLS)
        definitions, registry = resolve_tools(tool_names)
        set_tool_context(
            ToolContext(
                project_root=self.project_root,
                session_dir=session_dir,
                console=self.console,
                verbose=self.verbose,
            )
        )

        tool_calls = 0
        tokens_before = self.usage_tracker.total_tokens if self.usage_tracker else 0

        def _on_tool(name: str, arguments: dict, result: str) -> None:
            nonlocal tool_calls
            tool_calls += 1
            if self.on_progress is not None:
                used = (
                    (self.usage_tracker.total_tokens - tokens_before)
                    if self.usage_tracker
                    else 0
                )
                self.on_progress(task.id, tool_calls, used)
            if self.verbose and self.console is not None:
                preview = result if len(result) < 240 else result[:240] + "…"
                self.console.print(f"[dim]{task.profile} · {name}({arguments}) → {preview}[/dim]")

        try:
            system_prompt = load_profile(task.profile, self.project_root)
            text = await react_loop(
                client=self.client,
                model=self.model,
                system_prompt=system_prompt,
                user_message=_report_instructions(task),
                tools=definitions,
                tool_registry=registry,
                max_turns=self.max_turns,
                on_tool_call=_on_tool,
                usage_tracker=self.usage_tracker,
            )
            try:
                report = parse_model_json(SubReport, text)
            except ValidationError:
                report = _fallback_report(task, text)
        except Exception as exc:
            report = _fallback_report(task, "", error=str(exc))

        tokens_used = (
            self.usage_tracker.total_tokens - tokens_before if self.usage_tracker else 0
        )
        if self.on_progress is not None:
            self.on_progress(task.id, tool_calls, tokens_used)

        markdown = render_sub_report_markdown(report)
        save_text(session_dir / "sub_reports" / f"{task.id}_{task.profile}.md", markdown)
        return report
