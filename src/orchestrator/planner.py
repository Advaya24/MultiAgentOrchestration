"""Bounded team-planner executors that can propose, but never persist, work."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import ClassVar

from dotenv import load_dotenv
from pydantic import BaseModel, Field
from strands import Agent
from strands.models import GeminiModel
from strands.sandbox import Sandbox

from src.agents.sandbox import worker_sandbox
from src.agents.tracing import AgentTraceCallback, configure_local_otel_trace
from src.state.models import CompletionProposal, PlannerPlan, PlannedTaskDraft, TaskRecord, TaskReform
from src.state.run_store import RunStore


PLANNER_TASK_TYPES = frozenset(
    {
        "discover_sources",
        "discover_arxiv",
        "extract_evidence",
        "assess_claims",
        "write_brief",
        "revise_artifact",
        "resolve_conflict",
    }
)
PLANNER_CAPABILITIES = frozenset(
    {"task-handoff", "source-discovery", "evidence-extraction", "claim-assessment", "brief-writing"}
)
DEFAULT_PLANNER_MODEL = "gemini-3.5-flash-lite"
DEFAULT_MISTRAL_PLANNER_MODEL = "mistral-small-2506"
PLANNER_MAX_TURNS = 16
PLANNER_MAX_TOKENS = 16_000


class PlannerResponse(BaseModel):
    """Structured, untrusted reasoning output from the planner agent."""

    summary: str
    plan: PlannerPlan


class PlannerExecutor:
    """Common interface for deterministic and live planner implementations."""

    def execute(self, store: RunStore, task: TaskRecord, run_id: str) -> CompletionProposal:
        raise NotImplementedError


@dataclass
class FixturePlannerExecutor(PlannerExecutor):
    """Deterministic initial decomposition for local lifecycle tests."""

    sandbox: Sandbox

    def execute(self, store: RunStore, task: TaskRecord, run_id: str) -> CompletionProposal:
        if task.type == "planner_review":
            if task.review_of_task_id is None:
                raise ValueError("Planner review requires a blocked task reference.")
            blocked = store.read_task(task.review_of_task_id)
            plan = PlannerPlan(
                summary="Fixture planner re-formed the blocked task.",
                reforms=[
                    TaskReform(
                        target_task_id=blocked.id,
                        instruction=blocked.instruction,
                        required_capabilities=blocked.required_capabilities,
                        input_artifacts=blocked.input_artifacts,
                        acceptance_criteria=blocked.acceptance_criteria,
                    )
                ],
            )
        else:
            plan = PlannerPlan(
                summary="Split the request into independent source-discovery lanes.",
                tasks=[
                    PlannedTaskDraft(
                        key="primary-sources",
                        type="discover_sources",
                        instruction=f"Find primary and authoritative sources for: {task.instruction}",
                        required_capabilities=["source-discovery", "task-handoff"],
                        acceptance_criteria=["Return source records with URL and provenance."],
                    ),
                    PlannedTaskDraft(
                        key="independent-sources",
                        type="discover_sources",
                        instruction=f"Find independent corroborating sources for: {task.instruction}",
                        required_capabilities=["source-discovery", "task-handoff"],
                        acceptance_criteria=["Return source records distinct from the primary lane."],
                    ),
                ],
            )
        return CompletionProposal(
            task_id=task.id,
            attempt=task.attempt,
            summary=plan.summary,
            planner_plan=plan,
            metrics={"executor": "fixture_planner"},
        )


@dataclass
class GeminiPlannerExecutor(PlannerExecutor):
    """Live planner with a sandbox boundary and no model-callable tools."""

    sandbox: Sandbox
    model_provider: ClassVar[str] = "gemini"

    @classmethod
    def from_container(cls, container: str, working_dir: str = "/workspace") -> "GeminiPlannerExecutor":
        return cls(sandbox=worker_sandbox(container, working_dir))

    def execute(self, store: RunStore, task: TaskRecord, run_id: str) -> CompletionProposal:
        load_dotenv()
        api_key_name = "GEMINI_API_KEY" if self.model_provider == "gemini" else "MISTRAL_API_KEY"
        api_key = os.environ.get(api_key_name)
        if not api_key:
            raise RuntimeError(f"{api_key_name} is required for {self.model_provider} planner mode.")
        configure_local_otel_trace(store.otel_trace_path(task.id, task.attempt))
        if self.model_provider == "gemini":
            model = GeminiModel(
                client_args={"api_key": api_key},
                model_id=os.environ.get("GEMINI_MODEL", DEFAULT_PLANNER_MODEL),
                params={"max_output_tokens": PLANNER_MAX_TOKENS},
            )
        elif self.model_provider == "mistral":
            from strands.models.mistral import MistralModel

            model = MistralModel(
                api_key=api_key,
                model_id=os.environ.get("MISTRAL_MODEL", DEFAULT_MISTRAL_PLANNER_MODEL),
                max_tokens=PLANNER_MAX_TOKENS,
            )
        else:
            raise ValueError(f"Unsupported model provider: {self.model_provider}")
        agent = Agent(
            model=model,
            system_prompt=(
                "You are a research team planner. Produce a small, dependency-aware plan only. "
                "Do not claim research findings. Use only the allowed task types and capabilities. "
                "Local task keys must be unique and dependencies must name local keys. For a planner_review, "
                "return exactly one TaskReform for the referenced blocked task and no new plan tasks."
            ),
            tools=[],
            sandbox=self.sandbox,
            callback_handler=AgentTraceCallback(run_id=run_id, task_id=task.id, profile="team_planner"),
            trace_attributes={"run.id": run_id, "task.id": task.id, "profile": "team_planner"},
        )
        envelope = (
            f"Planner task ID: {task.id}\nType: {task.type}\nRequest: {task.instruction}\n"
            f"Blocked task to reform: {task.review_of_task_id}\n"
            f"Permitted input artifact IDs: {task.input_artifacts}\n"
            f"Allowed task types: {sorted(PLANNER_TASK_TYPES)}\n"
            f"Allowed capabilities: {sorted(PLANNER_CAPABILITIES)}\n"
            "Return a structured PlannerResponse. Keep the plan to at most 8 tasks."
        )
        try:
            result = agent(
                envelope,
                structured_output_model=PlannerResponse,
                idempotency_token=f"planner:{task.id}:{task.attempt}",
                limits={"turns": PLANNER_MAX_TURNS, "total_tokens": PLANNER_MAX_TOKENS},
            )
            response = result.structured_output
            if not isinstance(response, PlannerResponse):
                raise RuntimeError(f"{self.model_provider} planner returned no structured plan.")
            return CompletionProposal(
                task_id=task.id,
                attempt=task.attempt,
                summary=response.summary,
                planner_plan=response.plan,
                metrics={"executor": f"{self.model_provider}_planner", "stop_reason": result.stop_reason or "unknown"},
            )
        finally:
            agent.cleanup()


class MistralPlannerExecutor(GeminiPlannerExecutor):
    """Live Mistral planner using the same bounded planning contract."""

    model_provider: ClassVar[str] = "mistral"
