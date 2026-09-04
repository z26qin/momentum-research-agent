from __future__ import annotations

import pytest

from momentum_research_agent.tools.engine_pipeline import clear_pipeline_cache
from momentum_research_agent.tools.registry import clear_tool_context


@pytest.fixture(autouse=True)
def _isolate_engine_runtime() -> None:
    """Drop leaked ToolContext and in-memory pipeline cache between tests."""
    clear_tool_context()
    clear_pipeline_cache()
    yield
    clear_tool_context()
    clear_pipeline_cache()
