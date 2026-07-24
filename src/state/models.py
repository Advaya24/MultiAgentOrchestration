"""Serializable contracts for task-board handoffs."""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class TaskStatus(str, Enum):
    """States controlled exclusively by the scheduler."""

    PENDING = "pending"
    READY = "ready"
    CLAIMED = "claimed"
    AWAITING_REVIEW = "awaiting_review"
    COMPLETE = "complete"
    BLOCKED = "blocked"
    FAILED = "failed"
    STALE = "stale"
    CANCELLED = "cancelled"


class Lease(BaseModel):
    """A time-limited scheduler-issued claim."""

    worker_id: str
    expires_at: datetime


class TaskRecord(BaseModel):
    """Durable Markdown task front matter and human instruction."""

    id: str
    type: str
    status: TaskStatus = TaskStatus.PENDING
    depends_on: list[str] = Field(default_factory=list)
    priority: int = 0
    lease: Lease | None = None
    attempt: int = 0
    required_capabilities: list[str] = Field(default_factory=list)
    input_artifacts: list[str] = Field(default_factory=list)
    output_artifacts: list[str] = Field(default_factory=list)
    output_contract: str = "artifact/v1"
    review_required: bool = False
    review_of_task_id: str | None = None
    instruction: str
    acceptance_criteria: list[str] = Field(default_factory=list)


class ArtifactDraft(BaseModel):
    """Worker-proposed immutable artifact, validated by the scheduler."""

    kind: str
    summary: str
    payload: dict[str, object] = Field(default_factory=dict)
    input_artifacts: list[str] = Field(default_factory=list)


class TaskDraft(BaseModel):
    """A follow-up task proposal that cannot bypass scheduler validation."""

    type: str
    instruction: str
    required_capabilities: list[str] = Field(default_factory=list)
    input_artifacts: list[str] = Field(default_factory=list)
    review_required: bool = False


class PlannedTaskDraft(BaseModel):
    """Lead-proposed task expressed with local keys, not durable IDs."""

    key: str
    type: str
    instruction: str
    required_capabilities: list[str] = Field(default_factory=list)
    depends_on_keys: list[str] = Field(default_factory=list)
    input_artifacts: list[str] = Field(default_factory=list)
    acceptance_criteria: list[str] = Field(default_factory=list)
    review_required: bool = False


class LeadPlan(BaseModel):
    """Untrusted lead output that the scheduler validates before persistence."""

    summary: str
    tasks: list[PlannedTaskDraft] = Field(default_factory=list)
    reforms: list["TaskReform"] = Field(default_factory=list)


class TaskReform(BaseModel):
    """A lead-approved replacement envelope for one blocked task."""

    target_task_id: str
    instruction: str
    required_capabilities: list[str] = Field(default_factory=list)
    input_artifacts: list[str] = Field(default_factory=list)
    acceptance_criteria: list[str] = Field(default_factory=list)


class CompletionProposal(BaseModel):
    """Compact cross-runtime worker result written to the inbox."""

    task_id: str
    attempt: int
    status: str = "complete"
    summary: str
    artifacts: list[ArtifactDraft] = Field(default_factory=list)
    follow_up_tasks: list[TaskDraft] = Field(default_factory=list)
    lead_plan: LeadPlan | None = None
    metrics: dict[str, int | float | str] = Field(default_factory=dict)
