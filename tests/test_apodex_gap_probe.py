"""Regression tests for the Apodex-gap evidence probe."""

from __future__ import annotations

import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROBE_PATH = ROOT / "scripts" / "probe_apodex_gap.py"


def _load_probe():
    spec = importlib.util.spec_from_file_location("probe_apodex_gap", PROBE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _pattern(signal_id: str) -> str:
    probe = _load_probe()
    for _dimension, sid, _pathspec, pattern in probe.SIGNALS:
        if sid == signal_id:
            return pattern
    raise AssertionError(f"unknown signal {signal_id}")


def test_probe_cli_emits_seven_dimensions() -> None:
    result = subprocess.run(
        [sys.executable, str(PROBE_PATH), "HEAD"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(result.stdout)
    probe = _load_probe()
    assert payload["ref"] == "HEAD"
    assert list(payload["dimensions"]) == list(probe.DIMENSIONS)
    assert {item["id"] for item in payload["signals"]} == {item[1] for item in probe.SIGNALS}


def test_head_still_has_task_board_scaffold() -> None:
    probe = _load_probe()
    summary = probe.summarize(probe.probe("HEAD"))
    assert "disk_task_board" in summary["coordination_scaling"]["present"]
    assert "unit_tests" in summary["eval_attribution"]["present"]
    assert "trajectory_log" in summary["training_loop"]["missing"]
    assert "prompt_evolution" in summary["training_loop"]["missing"]


def test_live_replan_ignores_out_of_scope_prose() -> None:
    pattern = _pattern("live_replan")
    assert re.search(pattern, "class AgentBus:")
    assert re.search(pattern, "async def replan(self):")
    assert re.search(pattern, "def staged_return():")
    assert re.search(pattern, "AgentBus is still out of scope.") is None
    assert re.search(pattern, "there is no AgentBus.") is None


def test_training_loop_still_absent_on_head() -> None:
    """PR #2 does not add this; a hit here means main actually moved toward self-improvement."""
    probe = _load_probe()
    summary = probe.summarize(probe.probe("HEAD"))
    assert summary["training_loop"]["present"] == []
