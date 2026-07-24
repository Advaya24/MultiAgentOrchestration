"""Deterministic checks for the optional standalone example."""

from __future__ import annotations

import sys

import pytest

from examples import base_agent


def test_main_requires_a_prompt(monkeypatch: pytest.MonkeyPatch) -> None:
    """The command fails clearly before attempting model initialization."""
    monkeypatch.setattr(sys, "argv", ["base-agent"])

    with pytest.raises(SystemExit, match="Usage: .*Your prompt"):
        base_agent.main()


def test_main_rejects_unknown_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["base-agent", "--provider", "unknown", "Hello"])

    with pytest.raises(SystemExit, match="--provider must be gemini or mistral"):
        base_agent.main()
