"""Capability-selected worker profiles and bounded application skills."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


SKILLS_ROOT = Path(__file__).with_name("skills")
MAX_WORKER_TURNS = 64
MAX_WORKER_TOKENS = 64_000


@dataclass(frozen=True)
class WorkerProfile:
    """Non-negotiable capability and context limits for one task class."""

    name: str
    capabilities: frozenset[str]
    skill_names: tuple[str, ...]
    max_turns: int
    max_tokens: int
    enable_ddg_search: bool = False
    enable_arxiv: bool = False
    supported_task_types: frozenset[str] = frozenset()

    @property
    def skill_paths(self) -> list[Path]:
        return [SKILLS_ROOT / name for name in self.skill_names]


PROFILES = (
    WorkerProfile(
        name="web_discovery",
        capabilities=frozenset({"source-discovery", "task-handoff"}),
        skill_names=("task-handoff", "source-discovery"),
        max_turns=MAX_WORKER_TURNS,
        max_tokens=MAX_WORKER_TOKENS,
        enable_ddg_search=True,
        supported_task_types=frozenset({"discover_sources"}),
    ),
    WorkerProfile(
        name="arxiv_discovery",
        capabilities=frozenset({"source-discovery", "task-handoff"}),
        skill_names=("task-handoff", "source-discovery"),
        max_turns=MAX_WORKER_TURNS,
        max_tokens=MAX_WORKER_TOKENS,
        enable_arxiv=True,
        supported_task_types=frozenset({"discover_arxiv"}),
    ),
    WorkerProfile(
        name="evidence",
        capabilities=frozenset({"evidence-extraction", "task-handoff"}),
        skill_names=("task-handoff", "evidence-extraction"),
        max_turns=MAX_WORKER_TURNS,
        max_tokens=MAX_WORKER_TOKENS,
    ),
    WorkerProfile(
        name="assessment",
        capabilities=frozenset({"claim-assessment", "task-handoff"}),
        skill_names=("task-handoff", "claim-assessment"),
        max_turns=MAX_WORKER_TURNS,
        max_tokens=MAX_WORKER_TOKENS,
    ),
    WorkerProfile(
        name="writer",
        capabilities=frozenset({"brief-writing", "task-handoff"}),
        skill_names=("task-handoff", "brief-writing"),
        max_turns=MAX_WORKER_TURNS,
        max_tokens=MAX_WORKER_TOKENS,
    ),
)


def select_profile(required_capabilities: list[str], task_type: str | None = None) -> WorkerProfile:
    """Return the narrowest profile satisfying a task's declared requirements."""
    required = set(required_capabilities)
    candidates = [profile for profile in PROFILES if required.issubset(profile.capabilities)]
    if task_type:
        typed_candidates = [profile for profile in candidates if task_type in profile.supported_task_types]
        if typed_candidates:
            candidates = typed_candidates
    if not candidates:
        raise ValueError(f"No worker profile supports capabilities: {sorted(required)}")
    return min(candidates, key=lambda profile: (len(profile.capabilities), profile.name))
