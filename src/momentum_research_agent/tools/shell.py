"""Run a short shell command inside the project directory."""

from __future__ import annotations

import asyncio

from momentum_research_agent.tools.registry import get_tool_context, register_tool

_TIMEOUT_SECONDS = 30


@register_tool(
    name="shell",
    description=(
        "Run a shell command in the project directory (30s timeout). "
        "Use for short Python scripts, file listings, or data checks. "
        "The command is printed to the terminal before it runs."
    ),
    parameters={
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": "Shell command to execute.",
            }
        },
        "required": ["command"],
    },
)
async def shell(command: str) -> str:
    ctx = get_tool_context()
    cwd = ctx.project_root
    console = ctx.console
    if console is not None:
        console.print(f"[yellow]shell ▶[/yellow] {command}")
    else:
        print(f"shell ▶ {command}")

    process = await asyncio.create_subprocess_shell(
        command,
        cwd=str(cwd),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=_TIMEOUT_SECONDS)
    except TimeoutError:
        process.kill()
        await process.communicate()
        return f"Command timed out after {_TIMEOUT_SECONDS}s: {command}"

    out = stdout.decode("utf-8", errors="replace")
    err = stderr.decode("utf-8", errors="replace")
    parts = [f"exit_code={process.returncode}"]
    if out.strip():
        parts.append(f"stdout:\n{out}")
    if err.strip():
        parts.append(f"stderr:\n{err}")
    return "\n\n".join(parts)
