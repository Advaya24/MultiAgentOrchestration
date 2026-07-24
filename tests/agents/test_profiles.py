"""Discovery tool profiles must select explicitly scoped discovery paths."""

from __future__ import annotations

from src.agents.profiles import select_profile


def test_web_discovery_uses_ddg_search_without_arxiv_mcp() -> None:
    profile = select_profile(["source-discovery", "task-handoff"], "discover_sources")

    assert profile.enable_ddg_search is True
    assert profile.enable_arxiv is False
    assert profile.max_turns == 64
    assert profile.max_tokens == 64_000


def test_arxiv_discovery_uses_mcp_without_ddg_search() -> None:
    profile = select_profile(["source-discovery", "task-handoff"], "discover_arxiv")

    assert profile.enable_ddg_search is False
    assert profile.enable_arxiv is True
