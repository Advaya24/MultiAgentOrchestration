"""Deterministic coverage for the team-lead proposal boundary."""

from __future__ import annotations

import pytest

from src.orchestrator.lead import FixtureLeadExecutor
from src.orchestrator.scheduler import Scheduler
from src.state.models import ArtifactDraft, CompletionProposal, LeadPlan, PlannedTaskDraft, TaskRecord, TaskReform, TaskStatus
from src.state.run_store import RunStore


def _claimed_lead(scheduler: Scheduler) -> TaskRecord:
    scheduler.create_task(
        TaskRecord(id="T-001", type="plan_research", instruction="Compare two durable orchestration designs.")
    )
    return scheduler.claim_task("T-001", "lead-1")


def test_fixture_lead_materializes_parallel_discovery_tasks(tmp_path) -> None:
    store = RunStore(tmp_path / "run")
    scheduler = Scheduler(store)
    lead_task = _claimed_lead(scheduler)

    proposal = FixtureLeadExecutor(sandbox=object()).execute(store, lead_task, "run")
    scheduler.accept_proposal(proposal)

    tasks = {task.id: task for task in store.list_tasks()}
    assert tasks["T-001"].status is TaskStatus.COMPLETE
    assert tasks["T-002"].type == "discover_sources"
    assert tasks["T-003"].type == "discover_sources"
    assert tasks["T-002"].status is TaskStatus.READY
    assert tasks["T-003"].status is TaskStatus.READY
    assert "lead_plan_materialized" in (store.run_dir / "events.md").read_text(encoding="utf-8")


def test_scheduler_translates_lead_local_dependencies(tmp_path) -> None:
    store = RunStore(tmp_path / "run")
    scheduler = Scheduler(store)
    lead_task = _claimed_lead(scheduler)
    proposal = CompletionProposal(
        task_id=lead_task.id,
        attempt=lead_task.attempt,
        summary="Plan sequential research.",
        lead_plan=LeadPlan(
            summary="Sequential plan.",
            tasks=[
                PlannedTaskDraft(
                    key="sources",
                    type="discover_sources",
                    instruction="Discover sources.",
                    required_capabilities=["source-discovery", "task-handoff"],
                ),
                PlannedTaskDraft(
                    key="evidence",
                    type="extract_evidence",
                    instruction="Extract evidence after discovery.",
                    required_capabilities=["evidence-extraction", "task-handoff"],
                    depends_on_keys=["sources"],
                ),
            ],
        ),
    )

    scheduler.accept_proposal(proposal)

    evidence = store.read_task("T-003")
    assert evidence.depends_on == ["T-002"]
    assert evidence.status is TaskStatus.PENDING


def test_scheduler_hands_dependency_artifacts_to_ready_downstream_task(tmp_path) -> None:
    store = RunStore(tmp_path / "run")
    scheduler = Scheduler(store)
    lead_task = _claimed_lead(scheduler)
    scheduler.accept_proposal(
        CompletionProposal(
            task_id=lead_task.id,
            attempt=lead_task.attempt,
            summary="Plan sequential research.",
            lead_plan=LeadPlan(
                summary="Sequential plan.",
                tasks=[
                    PlannedTaskDraft(
                        key="sources",
                        type="discover_sources",
                        instruction="Discover sources.",
                        required_capabilities=["source-discovery", "task-handoff"],
                    ),
                    PlannedTaskDraft(
                        key="evidence",
                        type="extract_evidence",
                        instruction="Extract evidence.",
                        required_capabilities=["evidence-extraction", "task-handoff"],
                        depends_on_keys=["sources"],
                    ),
                ],
            ),
        )
    )
    source_task = scheduler.claim_task("T-002", "source-worker")
    scheduler.accept_proposal(
        CompletionProposal(
            task_id=source_task.id,
            attempt=source_task.attempt,
            summary="Discovered sources.",
            artifacts=[ArtifactDraft(kind="source_discovery", summary="One source.")],
        )
    )

    evidence = store.read_task("T-003")
    assert evidence.status is TaskStatus.READY
    assert evidence.input_artifacts == ["A-001"]
    events = (store.run_dir / "events.md").read_text(encoding="utf-8")
    assert '"input_artifacts": ["A-001"]' in events


def test_scheduler_rejects_cyclic_lead_plan_without_writing_tasks(tmp_path) -> None:
    store = RunStore(tmp_path / "run")
    scheduler = Scheduler(store)
    lead_task = _claimed_lead(scheduler)
    proposal = CompletionProposal(
        task_id=lead_task.id,
        attempt=lead_task.attempt,
        summary="Invalid cycle.",
        lead_plan=LeadPlan(
            summary="Invalid cycle.",
            tasks=[
                PlannedTaskDraft(
                    key="one",
                    type="discover_sources",
                    instruction="One.",
                    required_capabilities=["source-discovery"],
                    depends_on_keys=["two"],
                ),
                PlannedTaskDraft(
                    key="two",
                    type="extract_evidence",
                    instruction="Two.",
                    required_capabilities=["evidence-extraction"],
                    depends_on_keys=["one"],
                ),
            ],
        ),
    )

    with pytest.raises(ValueError, match="dependency cycle"):
        scheduler.accept_proposal(proposal)

    assert [task.id for task in store.list_tasks()] == ["T-001"]
    assert store.read_task("T-001").status is TaskStatus.CLAIMED


def test_scheduler_opens_reform_review_after_artifact_less_worker_completion(tmp_path) -> None:
    store = RunStore(tmp_path / "run")
    scheduler = Scheduler(store)
    scheduler.create_task(
        TaskRecord(
            id="T-001",
            type="write_brief",
            instruction="Write a brief.",
            required_capabilities=["brief-writing", "task-handoff"],
        )
    )
    task = scheduler.claim_task("T-001", "writer-1")

    scheduler.accept_proposal(
        CompletionProposal(task_id=task.id, attempt=task.attempt, summary="No durable handoff.")
    )

    assert store.read_task("T-001").status is TaskStatus.BLOCKED
    review = store.read_task("T-002")
    assert review.review_of_task_id == "T-001"
    assert review.status is TaskStatus.READY


def test_scheduler_requeues_task_from_lead_reform(tmp_path) -> None:
    store = RunStore(tmp_path / "run")
    scheduler = Scheduler(store)
    scheduler.create_task(
        TaskRecord(
            id="T-001",
            type="write_brief",
            instruction="Write a brief.",
            required_capabilities=["brief-writing", "task-handoff"],
        )
    )
    first_attempt = scheduler.claim_task("T-001", "writer-1")
    scheduler.accept_proposal(
        CompletionProposal(task_id=first_attempt.id, attempt=first_attempt.attempt, summary="No durable handoff.")
    )
    review = scheduler.claim_task("T-002", "lead-1")
    scheduler.accept_proposal(
        CompletionProposal(
            task_id=review.id,
            attempt=review.attempt,
            summary="Re-form the task with its source handoff.",
            lead_plan=LeadPlan(
                summary="Re-form the task.",
                reforms=[
                    TaskReform(
                        target_task_id="T-001",
                        instruction="Write a sourced brief.",
                        required_capabilities=["brief-writing", "task-handoff"],
                        acceptance_criteria=["Use the permitted source artifact."],
                    )
                ],
            ),
        )
    )

    reformed = store.read_task("T-001")
    assert reformed.status is TaskStatus.READY
    assert reformed.instruction == "Write a sourced brief."
    assert reformed.acceptance_criteria == ["Use the permitted source artifact."]


def test_scheduler_reassigns_immediately_after_first_worker_exit_failure(tmp_path) -> None:
    store = RunStore(tmp_path / "run")
    scheduler = Scheduler(store)
    scheduler.create_task(TaskRecord(id="T-001", type="discover_sources", instruction="Discover sources."))
    scheduler.claim_task("T-001", "worker-1")

    scheduler.record_worker_exit("T-001", return_code=1)

    task = store.read_task("T-001")
    assert task.status is TaskStatus.READY
    assert task.lease is None
    assert "worker_failure_reassigned" in (store.run_dir / "events.md").read_text(encoding="utf-8")


def test_scheduler_blocks_second_worker_exit_failure_and_opens_lead_review(tmp_path) -> None:
    store = RunStore(tmp_path / "run")
    scheduler = Scheduler(store)
    scheduler.create_task(TaskRecord(id="T-001", type="discover_sources", instruction="Discover sources."))
    scheduler.claim_task("T-001", "worker-1")
    scheduler.record_worker_exit("T-001", return_code=1)
    scheduler.claim_task("T-001", "worker-2")

    scheduler.record_worker_exit("T-001", return_code=1)

    assert store.read_task("T-001").status is TaskStatus.BLOCKED
    assert store.read_task("T-002").type == "lead_review"


def test_worker_exit_event_links_to_attempt_log(tmp_path) -> None:
    store = RunStore(tmp_path / "run")
    scheduler = Scheduler(store)
    scheduler.create_task(TaskRecord(id="T-001", type="discover_sources", instruction="Discover sources."))
    scheduler.claim_task("T-001", "worker-1")

    scheduler.record_worker_exit("T-001", return_code=1, log_path="logs/t-001-attempt-1.log")

    events = (store.run_dir / "events.md").read_text(encoding="utf-8")
    assert '"log_path": "logs/t-001-attempt-1.log"' in events
