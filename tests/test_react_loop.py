from __future__ import annotations

from types import SimpleNamespace

import pytest

from momentum_research_agent.agents.react_loop import react_loop
from momentum_research_agent.models.schemas import UsageSummary


class FakeFunction:
    def __init__(self, name: str, arguments: str) -> None:
        self.name = name
        self.arguments = arguments


class FakeToolCall:
    def __init__(self, call_id: str, name: str, arguments: str) -> None:
        self.id = call_id
        self.function = FakeFunction(name, arguments)


class FakeMessage:
    def __init__(self, content: str | None = None, tool_calls: list | None = None) -> None:
        self.content = content
        self.tool_calls = tool_calls


class FakeUsage:
    def __init__(self, prompt_tokens: int = 10, completion_tokens: int = 5) -> None:
        self.prompt_tokens = prompt_tokens
        self.completion_tokens = completion_tokens


class FakeResponse:
    def __init__(self, message: FakeMessage) -> None:
        self.choices = [SimpleNamespace(message=message)]
        self.usage = FakeUsage()


class FakeCompletions:
    def __init__(self, responses: list[FakeResponse]) -> None:
        self._responses = list(responses)
        self.calls: list[dict] = []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        if not self._responses:
            raise AssertionError("unexpected extra LLM call")
        return self._responses.pop(0)


class FakeClient:
    def __init__(self, responses: list[FakeResponse]) -> None:
        self.completions = FakeCompletions(responses)
        self.chat = SimpleNamespace(completions=self.completions)


@pytest.mark.asyncio
async def test_two_turn_tool_then_text() -> None:
    observed: list[tuple[str, dict, str]] = []

    async def ping(query: str) -> str:
        return f"pong:{query}"

    client = FakeClient(
        [
            FakeResponse(
                FakeMessage(
                    content="",
                    tool_calls=[FakeToolCall("c1", "ping", '{"query": "nvda"}')],
                )
            ),
            FakeResponse(FakeMessage(content="Final view: rotation, not crash.")),
        ]
    )
    usage = UsageSummary()
    text = await react_loop(
        client=client,  # type: ignore[arg-type]
        model="deepseek-chat",
        system_prompt="You are a tester.",
        user_message="Investigate NVDA.",
        tools=[{"type": "function", "function": {"name": "ping"}}],
        tool_registry={"ping": ping},
        on_tool_call=lambda name, args, result: observed.append((name, args, result)),
        usage_tracker=usage,
    )

    assert text == "Final view: rotation, not crash."
    assert observed == [("ping", {"query": "nvda"}, "pong:nvda")]
    assert len(client.completions.calls) == 2
    second_messages = client.completions.calls[1]["messages"]
    tool_messages = [msg for msg in second_messages if msg["role"] == "tool"]
    assert tool_messages
    assert tool_messages[0]["content"] == "pong:nvda"
    assert usage.prompt_tokens == 20
    assert usage.completion_tokens == 10


@pytest.mark.asyncio
async def test_max_turns_cutoff() -> None:
    async def ping(query: str) -> str:
        return query

    responses = [
        FakeResponse(
            FakeMessage(
                content="still thinking",
                tool_calls=[FakeToolCall(f"c{i}", "ping", '{"query": "x"}')],
            )
        )
        for i in range(3)
    ]
    client = FakeClient(responses)
    text = await react_loop(
        client=client,  # type: ignore[arg-type]
        model="deepseek-chat",
        system_prompt="sys",
        user_message="go",
        tools=[],
        tool_registry={"ping": ping},
        max_turns=2,
    )
    assert "stopped after 2 turns" in text or text == "still thinking"
    assert len(client.completions.calls) == 2


@pytest.mark.asyncio
async def test_tool_error_is_returned_to_model() -> None:
    async def boom() -> str:
        raise RuntimeError("disk full")

    client = FakeClient(
        [
            FakeResponse(
                FakeMessage(
                    tool_calls=[FakeToolCall("c1", "boom", "{}")],
                )
            ),
            FakeResponse(FakeMessage(content="Recovered after tool error.")),
        ]
    )
    text = await react_loop(
        client=client,  # type: ignore[arg-type]
        model="deepseek-chat",
        system_prompt="sys",
        user_message="go",
        tools=[],
        tool_registry={"boom": boom},
    )
    assert text == "Recovered after tool error."
    tool_messages = [
        msg for msg in client.completions.calls[1]["messages"] if msg["role"] == "tool"
    ]
    assert tool_messages
    assert "RuntimeError" in tool_messages[0]["content"]
    assert "disk full" in tool_messages[0]["content"]
