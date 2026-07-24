"""Boundary checks for explicit web-discovery tools."""

from __future__ import annotations

import pytest

from src.agents.tools import _public_http_url_error, source_discovery_tools


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://example.org/report", None),
        ("http://[::1]/", "private or reserved IP addresses are not permitted."),
        ("http://127.0.0.1/", "private or reserved IP addresses are not permitted."),
        ("https://localhost/", "local hosts are not permitted."),
        ("file:///etc/passwd", "URL must be an absolute http or https address."),
    ],
)
def test_web_fetch_only_accepts_public_http_urls(url: str, expected: str | None) -> None:
    assert _public_http_url_error(url) == expected


def test_source_discovery_exposes_only_search_and_fetch_tools() -> None:
    tools = source_discovery_tools(sandbox=object())

    assert [tool.tool_name for tool in tools] == ["ddg_web_search", "web_fetch"]
