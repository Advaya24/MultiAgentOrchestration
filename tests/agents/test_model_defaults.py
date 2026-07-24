"""Live providers retain explicit, stable model defaults."""

from __future__ import annotations

from src.agents.factory import DEFAULT_MISTRAL_MODEL, DEFAULT_MODEL
from src.orchestrator.planner import DEFAULT_MISTRAL_PLANNER_MODEL, DEFAULT_PLANNER_MODEL


def test_planner_and_workers_share_flash_lite_default() -> None:
    assert DEFAULT_MODEL == "gemini-3.5-flash-lite"
    assert DEFAULT_PLANNER_MODEL == DEFAULT_MODEL


def test_planner_and_workers_share_mistral_default() -> None:
    assert DEFAULT_MISTRAL_MODEL == "mistral-small-2506"
    assert DEFAULT_MISTRAL_PLANNER_MODEL == DEFAULT_MISTRAL_MODEL
