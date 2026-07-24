"""Bounded team-lead executors that can propose, but never persist, work."""

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
from src.state.models import CompletionProposal, LeadPlan, PlannedTaskDraft, TaskRecord, TaskReform
from src.state.run_store import RunStore


LEAD_TASK_TYPES = frozenset(
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
LEAD_CAPABILITIES = frozenset(
    {"task-handoff", "source-discovery", "evidence-extraction", "claim-assessment", "brief-writing"}
)
DEFAULT_LEAD_MODEL = "gemini-3.5-flash-lite"
DEFAULT_MISTRAL_LEAD_MODEL = "mistral-small-2506"
LEAD_MAX_TURNS = 16
LEAD_MAX_TOKENS = 16_000


class LeadResponse(BaseModel):
    """Structured, untrusted reasoning output from the lead agent."""

    summary: str
    plan: LeadPlan


class LeadExecutor:
    """Common interface for deterministic and live lead implementations."""

    def execute(self, store: RunStore, task: TaskRecord, run_id: str) -> CompletionProposal:
        raise NotImplementedError


@dataclass
class FixtureLeadExecutor(LeadExecutor):
    """Deterministic initial decomposition for local lifecycle tests."""

    sandbox: Sandbox

    def execute(self, store: RunStore, task: TaskRecord, run_id: str) -> CompletionProposal:
        if task.type == "lead_review":
            if task.review_of_task_id is None:
                raise ValueError("Lead review requires a blocked task reference.")
            blocked = store.read_task(task.review_of_task_id)
            plan = LeadPlan(
                summary="Fixture lead re-formed the blocked task.",
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
            plan = LeadPlan(
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
            lead_plan=plan,
            metrics={"executor": "fixture_lead"},
        )


@dataclass
class GeminiLeadExecutor(LeadExecutor):
    """Live lead with a sandbox boundary and no model-callable tools."""

    sandbox: Sandbox
    model_provider: ClassVar[str] = "gemini"

    @classmethod
    def from_container(cls, container: str, working_dir: str = "/workspace") -> "GeminiLeadExecutor":
        return cls(sandbox=worker_sandbox(container, working_dir))

    def execute(self, store: RunStore, task: TaskRecord, run_id: str) -> CompletionProposal:
        load_dotenv()
        api_key_name = "GEMINI_API_KEY" if self.model_provider == "gemini" else "MISTRAL_API_KEY"
        api_key = os.environ.get(api_key_name)
        if not api_key:
            raise RuntimeError(f"{api_key_name} is required for {self.model_provider} lead mode.")
        configure_local_otel_trace(store.otel_trace_path(task.id, task.attempt))
        if self.model_provider == "gemini":
            model = GeminiModel(
                client_args={"api_key": api_key},
                model_id=os.environ.get("GEMINI_MODEL", DEFAULT_LEAD_MODEL),
                params={"max_output_tokens": LEAD_MAX_TOKENS},
            )
        elif self.model_provider == "mistral":
            from strands.models.mistral import MistralModel

            model = MistralModel(
                api_key=api_key,
                model_id=os.environ.get("MISTRAL_MODEL", DEFAULT_MISTRAL_LEAD_MODEL),
                max_tokens=LEAD_MAX_TOKENS,
            )
        else:
            raise ValueError(f"Unsupported model provider: {self.model_provider}")
        agent = Agent(
            model=model,
            system_prompt=(
                "You are a research team lead. Produce a small, dependency-aware plan only. "
                "Do not claim research findings. Use only the allowed task types and capabilities. "
                "Local task keys must be unique and dependencies must name local keys. For a lead_review, "
                "return exactly one TaskReform for the referenced blocked task and no new plan tasks."
            ),
            tools=[],
            sandbox=self.sandbox,
            callback_handler=AgentTraceCallback(run_id=run_id, task_id=task.id, profile="team_lead"),
            trace_attributes={"run.id": run_id, "task.id": task.id, "profile": "team_lead"},
        )
        envelope = (
            f"Lead task ID: {task.id}\nType: {task.type}\nRequest: {task.instruction}\n"
            f"Blocked task to reform: {task.review_of_task_id}\n"
            f"Permitted input artifact IDs: {task.input_artifacts}\n"
            f"Allowed task types: {sorted(LEAD_TASK_TYPES)}\n"
            f"Allowed capabilities: {sorted(LEAD_CAPABILITIES)}\n"
            "Return a structured LeadResponse. Keep the plan to at most 8 tasks."
        )
        try:
            result = agent(
                envelope,
                structured_output_model=LeadResponse,
                idempotency_token=f"lead:{task.id}:{task.attempt}",
                limits={"turns": LEAD_MAX_TURNS, "total_tokens": LEAD_MAX_TOKENS},
            )
            response = result.structured_output
            if not isinstance(response, LeadResponse):
                raise RuntimeError(f"{self.model_provider} lead returned no structured plan.")
            return CompletionProposal(
                task_id=task.id,
                attempt=task.attempt,
                summary=response.summary,
                lead_plan=response.plan,
                metrics={"executor": f"{self.model_provider}_lead", "stop_reason": result.stop_reason or "unknown"},
            )
        finally:
            agent.cleanup()


class MistralLeadExecutor(GeminiLeadExecutor):
    """Live Mistral lead using the same bounded planning contract."""

    model_provider: ClassVar[str] = "mistral"
