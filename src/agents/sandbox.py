"""Docker isolation without implicitly granting shell or filesystem tools."""

from __future__ import annotations

from strands.sandbox.docker import DockerSandbox


class RestrictedDockerSandbox(DockerSandbox):
    """Keep execution isolated while exposing only explicitly registered tools."""

    def get_tools(self) -> list[object]:
        return []


def worker_sandbox(container: str, working_dir: str = "/workspace") -> RestrictedDockerSandbox:
    """Create the common non-root Docker boundary for every executor."""
    return RestrictedDockerSandbox(container, working_dir=working_dir, user="worker")
