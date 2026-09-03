"""Generic ReAct loop: think → act → observe until the model stops calling tools."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from typing import Any, Optional

from openai import AsyncOpenAI

from momentum_research_agent.models.schemas import UsageSummary
from momentum_research_agent.tools.registry import call_tool

OnToolCall = Callable[[str, dict[str, Any], str], None]


def _record_usage(usage_tracker: UsageSummary | None, model: str, response: Any) -> None:
    usage = getattr(response, "usage", None)
    if usage_tracker is None or usage is None:
        return
    usage_tracker.add(
        model,
        int(getattr(usage, "prompt_tokens", 0) or 0),
        int(getattr(usage, "completion_tokens", 0) or 0),
    )


def _assistant_message(message: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "role": "assistant",
        "content": message.content or "",
    }
    tool_calls = getattr(message, "tool_calls", None) or []
    if tool_calls:
        payload["tool_calls"] = [
            {
                "id": call.id,
                "type": "function",
                "function": {
                    "name": call.function.name,
                    "arguments": call.function.arguments or "{}",
                },
            }
            for call in tool_calls
        ]
    return payload


def _parse_arguments(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return {"_raw": raw}
    return parsed if isinstance(parsed, dict) else {"value": parsed}


async def react_loop(
    client: AsyncOpenAI,
    model: str,
    system_prompt: str,
    user_message: str,
    tools: list[dict[str, Any]],
    tool_registry: Mapping[str, Callable[..., Any]],
    max_turns: int = 15,
    on_tool_call: Optional[OnToolCall] = None,
    usage_tracker: UsageSummary | None = None,
) -> str:
    """Run a native OpenAI-compatible tool-calling loop and return the final text."""
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message},
    ]
    last_text = ""

    for _turn in range(max_turns):
        kwargs: dict[str, Any] = {
            "model": model,
            "messages": messages,
        }
        if tools:
            kwargs["tools"] = tools
        response = await client.chat.completions.create(**kwargs)
        _record_usage(usage_tracker, model, response)

        message = response.choices[0].message
        last_text = message.content or last_text
        tool_calls = getattr(message, "tool_calls", None) or []
        messages.append(_assistant_message(message))

        if not tool_calls:
            return last_text or ""

        for call in tool_calls:
            name = call.function.name
            arguments = _parse_arguments(call.function.arguments)
            if name not in tool_registry:
                result = f"Unknown tool '{name}'. Available: {', '.join(sorted(tool_registry))}"
            else:
                try:
                    result = await call_tool(tool_registry[name], arguments)
                except Exception as exc:
                    result = f"Tool '{name}' raised {type(exc).__name__}: {exc}"
            if on_tool_call is not None:
                on_tool_call(name, arguments, result)
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call.id,
                    "content": result,
                }
            )

    return last_text or f"ReAct loop stopped after {max_turns} turns without a final answer."
