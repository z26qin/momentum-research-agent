"""Read local project files. Absolute paths outside the project are refused."""

from __future__ import annotations

import json
from pathlib import Path

from momentum_research_agent.tools.registry import get_tool_context, register_tool

_MAX_CHARS = 20_000
_CSV_ROWS = 100


def _is_inside(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _resolve_readable(path_str: str) -> Path:
    ctx = get_tool_context()
    project_root = ctx.project_root.resolve()
    raw = Path(path_str)

    if raw.is_absolute():
        resolved = raw.resolve()
        if not _is_inside(resolved, project_root):
            raise ValueError(
                f"Refusing to read {path_str}: absolute paths outside the project are blocked."
            )
        return resolved

    candidates: list[Path] = []
    if ctx.session_dir is not None:
        candidates.append((ctx.session_dir / raw).resolve())
    candidates.append((project_root / raw).resolve())
    candidates.append((Path.cwd() / raw).resolve())

    for candidate in candidates:
        if candidate.exists() and _is_inside(candidate, project_root):
            return candidate

    # Fall back to project-relative path even if missing so the error is clear.
    fallback = (project_root / raw).resolve()
    if not _is_inside(fallback, project_root):
        raise ValueError(f"Refusing to read {path_str}: path escapes the project directory.")
    return fallback


def _truncate(text: str) -> str:
    if len(text) <= _MAX_CHARS:
        return text
    return text[:_MAX_CHARS] + f"\n\n...[truncated at {_MAX_CHARS} characters]"


def _read_csv(path: Path) -> str:
    try:
        import pandas as pd
    except ImportError:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        return _truncate("\n".join(lines[: _CSV_ROWS + 1]))

    frame = pd.read_csv(path, nrows=_CSV_ROWS)
    return _truncate(frame.to_markdown(index=False))


def _read_json(path: Path) -> str:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return _truncate(json.dumps(payload, indent=2, ensure_ascii=False, default=str))


@register_tool(
    name="file_reader",
    description=(
        "Read a local file relative to the session or project directory. "
        "Supports .md, .txt, .csv (first 100 rows as a markdown table), and .json. "
        "Absolute paths outside the project are refused."
    ),
    parameters={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "File path relative to the session or project root.",
            }
        },
        "required": ["path"],
    },
)
async def file_reader(path: str) -> str:
    target = _resolve_readable(path)
    if not target.exists():
        return f"File not found: {path}"
    if not target.is_file():
        return f"Not a file: {path}"

    suffix = target.suffix.lower()
    if suffix == ".csv":
        return _read_csv(target)
    if suffix == ".json":
        return _read_json(target)
    if suffix in {".md", ".txt", ".py", ".toml", ".yml", ".yaml"}:
        return _truncate(target.read_text(encoding="utf-8", errors="replace"))
    return (
        f"Unsupported file type '{suffix}'. "
        "Supported: .md, .txt, .csv, .json."
    )
