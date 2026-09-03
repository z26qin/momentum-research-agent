"""Tool package. Importing this module registers every built-in tool."""

from momentum_research_agent.tools import (  # noqa: F401
    engine_query,
    file_reader,
    market_data,
    shell,
    web_search,
)
from momentum_research_agent.tools.registry import (
    ToolContext,
    get_tool_context,
    registered_names,
    resolve_tools,
    set_tool_context,
)

DEFAULT_TOOLS = [
    "engine_query",
    "market_data",
    "web_search",
    "file_reader",
    "shell",
]

PROFILE_TOOLS: dict[str, list[str]] = {
    "momentum_analyst": ["engine_query", "market_data", "web_search", "file_reader"],
    "credit_analyst": ["market_data", "web_search", "file_reader"],
    "macro_analyst": ["market_data", "web_search", "file_reader"],
    "flow_analyst": ["engine_query", "market_data", "web_search", "file_reader"],
    "technicals_analyst": ["market_data", "web_search", "file_reader"],
}

__all__ = [
    "DEFAULT_TOOLS",
    "PROFILE_TOOLS",
    "ToolContext",
    "get_tool_context",
    "registered_names",
    "resolve_tools",
    "set_tool_context",
]
