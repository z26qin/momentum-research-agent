from __future__ import annotations

import pytest

from momentum_research_agent.errors import UnauthorizedTool
from momentum_research_agent.tools import (
    DEFAULT_TOOLS,
    PROFILE_TOOLS,
    RESEARCH_PROFILES,
    authorize_research_tools,
    authorize_tools,
    registered_names,
    tools_for_profile,
)


def test_known_profile_resolves_only_allowlist() -> None:
    allowed = tools_for_profile("momentum_analyst")
    assert allowed == PROFILE_TOOLS["momentum_analyst"]
    assert "shell" not in allowed
    assert authorize_tools("credit_analyst") == [
        "market_data",
        "web_search",
        "file_reader",
    ]


def test_unknown_profile_rejected() -> None:
    with pytest.raises(UnauthorizedTool, match="Unknown profile"):
        tools_for_profile("quant_intern")
    with pytest.raises(UnauthorizedTool, match="Unknown profile"):
        authorize_tools("quant_intern")


def test_shell_not_in_default_research_tools() -> None:
    assert "shell" not in DEFAULT_TOOLS
    assert "shell" in registered_names()


def test_requested_unauthorized_tool_rejected() -> None:
    with pytest.raises(UnauthorizedTool, match="shell"):
        authorize_tools("momentum_analyst", ["engine_query", "shell"])


def test_verifier_is_authorized_but_not_a_research_profile() -> None:
    assert "verifier" not in RESEARCH_PROFILES
    assert "shell" not in authorize_tools("verifier")
    with pytest.raises(UnauthorizedTool, match="not a research profile"):
        authorize_research_tools("verifier")
