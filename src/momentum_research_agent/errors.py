"""Minimal typed failures for the ReAct runtime and tool authorization."""


class AgentRuntimeError(Exception):
    """Base class for bounded-agent runtime failures."""


class AgentDeadlineExceeded(AgentRuntimeError):
    """Overall run deadline or LLM call timeout was hit."""


class ToolExecutionTimeout(AgentRuntimeError):
    """A tool exceeded its per-call timeout."""


class UnauthorizedTool(AgentRuntimeError):
    """Profile unknown, or the model requested a tool not on its allowlist."""
