"""Fixture and live-provider task executors sharing one proposal contract."""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar, Protocol

from pydantic import BaseModel, Field
from strands.sandbox import Sandbox

from src.agents.factory import build_worker_agent
from src.agents.profiles import select_profile
from src.agents.sandbox import worker_sandbox
from src.state.models import ArtifactDraft, CompletionProposal, TaskDraft, TaskRecord
from src.state.run_store import RunStore


class WorkerResponse(BaseModel):
    """Model-owned portion of a completion proposal."""

    status: str = "complete"
    summary: str
    artifacts: list[ArtifactDraft] = Field(default_factory=list)
    follow_up_tasks: list[TaskDraft] = Field(default_factory=list)


class WorkerExecutor(Protocol):
    """Cross-runtime executor contract used by the task-runner subprocess."""

    def execute(self, store: RunStore, task: TaskRecord, run_id: str) -> CompletionProposal:
        """Return one compact proposal without mutating durable state."""


@dataclass
class FixtureWorkerExecutor:
    """Deterministic worker for lifecycle and recovery tests."""

    sandbox: Sandbox
    response_by_type: dict[str, WorkerResponse] | None = None

    def execute(self, store: RunStore, task: TaskRecord, run_id: str) -> CompletionProposal:
        response = (self.response_by_type or {}).get(task.type)
        if response is None:
            response = WorkerResponse(
                summary=f"Fixture completed {task.type}.",
                artifacts=[ArtifactDraft(kind=f"{task.type}/v1", summary=f"Fixture output for {task.id}.")],
            )
        return CompletionProposal(
            task_id=task.id,
            attempt=task.attempt,
            status=response.status,
            summary=response.summary,
            artifacts=response.artifacts,
            follow_up_tasks=response.follow_up_tasks,
            metrics={"executor": "fixture"},
        )


@dataclass
class GeminiWorkerExecutor:
    """Live executor; every fresh agent receives an explicit Docker sandbox."""

    sandbox: Sandbox
    model_provider: ClassVar[str] = "gemini"

    @classmethod
    def from_container(cls, container: str, working_dir: str = "/workspace") -> "GeminiWorkerExecutor":
        return cls(sandbox=worker_sandbox(container, working_dir))

    def execute(self, store: RunStore, task: TaskRecord, run_id: str) -> CompletionProposal:
        profile = select_profile(task.required_capabilities, task.type)
        agent = build_worker_agent(
            store=store,
            task=task,
            profile=profile,
            sandbox=self.sandbox,
            run_id=run_id,
            model_provider=self.model_provider,
        )
        envelope = (
            f"Task ID: {task.id}\nType: {task.type}\nInstruction: {task.instruction}\n"
            f"Acceptance criteria: {task.acceptance_criteria}\n"
            f"Permitted artifact IDs: {task.input_artifacts}\n"
            "Return the required structured completion response."
        )
        try:
            result = agent(
                envelope,
                structured_output_model=WorkerResponse,
                idempotency_token=f"{task.id}:{task.attempt}",
                limits={"turns": profile.max_turns, "total_tokens": profile.max_tokens},
            )
            response = result.structured_output
            if not isinstance(response, WorkerResponse):
                raise RuntimeError(f"{self.model_provider} worker returned no structured completion response.")
            metrics = {
                "executor": self.model_provider,
                "stop_reason": result.stop_reason or "unknown",
            }
            return CompletionProposal(
                task_id=task.id,
                attempt=task.attempt,
                status=response.status,
                summary=response.summary,
                artifacts=response.artifacts,
                follow_up_tasks=response.follow_up_tasks,
                metrics=metrics,
            )
        finally:
            agent.cleanup()


class MistralWorkerExecutor(GeminiWorkerExecutor):
    """Live Mistral executor using the same bounded worker contract."""

    model_provider: ClassVar[str] = "mistral"
