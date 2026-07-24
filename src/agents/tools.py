"""Narrow, scheduler-scoped tools exposed to worker agents."""

from __future__ import annotations

import json
import shlex
from ipaddress import ip_address
from urllib.parse import urlparse

from strands import tool
from strands.sandbox import Sandbox

from src.state.models import TaskRecord
from src.state.run_store import RunStore


def allowed_artifact_reader(store: RunStore, task: TaskRecord):
    """Create an agent tool that cannot read artifacts outside the envelope."""

    allowed = frozenset(task.input_artifacts)

    @tool
    def read_allowed_artifact(artifact_id: str) -> str:
        """Read one artifact explicitly permitted by the current task envelope."""
        if artifact_id not in allowed:
            return f"Denied: artifact {artifact_id} is not in this task's input_artifacts."
        return json.dumps(store.read_artifact(artifact_id), sort_keys=True)

    return read_allowed_artifact


def source_discovery_tools(sandbox: Sandbox) -> list[object]:
    """Create the bounded search and retrieval tools for web-discovery workers."""

    @tool
    async def ddg_web_search(query: str, max_results: int = 5) -> str:
        """Search DuckDuckGo for public sources; returns at most ten Markdown results."""
        cleaned_query = " ".join(query.split())
        if not cleaned_query:
            return "Denied: query must not be empty."
        if len(cleaned_query) > 500:
            return "Denied: query exceeds the 500-character limit."
        bounded_results = max(1, min(max_results, 10))
        command = (
            f"ddg-search --safe-search --max-results {bounded_results} "
            f"--max-retries 2 --max-retry-delay 5s {shlex.quote(cleaned_query)}"
        )
        result = await sandbox.execute(command, timeout=20)
        if result.exit_code != 0:
            return f"Search failed (exit {result.exit_code}): {result.stderr[-2_000:]}"
        return result.stdout[:12_000]

    @tool
    async def web_fetch(url: str) -> str:
        """Fetch one public HTTP(S) page as bounded Markdown for source verification."""
        reason = _public_http_url_error(url)
        if reason:
            return f"Denied: {reason}"
        result = await sandbox.execute(f"page-dump --timeout 20s {shlex.quote(url)}", timeout=25)
        if result.exit_code != 0:
            return f"Fetch failed (exit {result.exit_code}): {result.stderr[-2_000:]}"
        return result.stdout[:20_000]

    return [ddg_web_search, web_fetch]


def _public_http_url_error(url: str) -> str | None:
    """Reject malformed, local, and literal private-network fetch targets."""
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return "URL must be an absolute http or https address."
    hostname = parsed.hostname
    if hostname is None or hostname.lower() in {"localhost", "localhost.localdomain"}:
        return "local hosts are not permitted."
    try:
        if not ip_address(hostname).is_global:
            return "private or reserved IP addresses are not permitted."
    except ValueError:
        pass
    return None
