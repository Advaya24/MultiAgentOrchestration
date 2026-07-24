"""Deterministic task transitions, recovery, and focused invalidation."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from src.orchestrator.planner import PLANNER_CAPABILITIES, PLANNER_TASK_TYPES
from src.state.models import CompletionProposal, PlannerPlan, Lease, PlannedTaskDraft, TaskDraft, TaskRecord, TaskReform, TaskStatus
from src.state.run_store import RunStore


class Scheduler:
    """The only authority allowed to mutate durable task-board state."""

    def __init__(self, store: RunStore, lease_seconds: int = 300) -> None:
        self.store = store
        self.lease_seconds = lease_seconds

    def create_task(self, task: TaskRecord) -> None:
        self.store.create_task(task)
        self.store.append_event("task_created", task_id=task.id, task_type=task.type)
        self.refresh_ready_tasks()
        self.store.render_board()

    def refresh_ready_tasks(self) -> None:
        tasks = {task.id: task for task in self.store.list_tasks()}
        for task in tasks.values():
            if task.status is not TaskStatus.PENDING:
                continue
            if all(tasks[dependency].status is TaskStatus.COMPLETE for dependency in task.depends_on):
                dependency_artifacts = [
                    artifact_id
                    for dependency in task.depends_on
                    for artifact_id in tasks[dependency].output_artifacts
                ]
                new_inputs = self._merge_artifact_ids(task.input_artifacts, dependency_artifacts)
                if new_inputs != task.input_artifacts:
                    task.input_artifacts = new_inputs
                task.status = TaskStatus.READY
                self.store.update_task(task)
                self.store.append_event(
                    "task_ready",
                    task_id=task.id,
                    input_artifacts=task.input_artifacts,
                )

    def claim_task(self, task_id: str, worker_id: str, now: datetime | None = None) -> TaskRecord:
        now = now or datetime.now(timezone.utc)
        task = self.store.read_task(task_id)
        if task.status is not TaskStatus.READY:
            raise ValueError(f"Task {task_id} is not ready")
        task.status = TaskStatus.CLAIMED
        task.attempt += 1
        task.lease = Lease(worker_id=worker_id, expires_at=now + timedelta(seconds=self.lease_seconds))
        self.store.update_task(task)
        self.store.append_event("task_claimed", task_id=task.id, worker_id=worker_id, attempt=task.attempt)
        self.store.render_board()
        return task

    def process_inbox(self) -> list[str]:
        completed: list[str] = []
        for proposal in self.store.consume_proposals():
            self.accept_proposal(proposal)
            completed.append(proposal.task_id)
        return completed

    def accept_proposal(self, proposal: CompletionProposal) -> None:
        task = self.store.read_task(proposal.task_id)
        if task.status is not TaskStatus.CLAIMED or task.attempt != proposal.attempt:
            self.store.append_event("proposal_rejected", task_id=proposal.task_id, reason="stale_or_unclaimed")
            return
        if proposal.status == "blocked":
            task.status = TaskStatus.BLOCKED
            task.lease = None
            self.store.update_task(task)
            self.store.append_event("task_blocked", task_id=task.id, summary=proposal.summary)
            self._create_planner_review(task)
            self.store.render_board()
            return
        if proposal.status != "complete":
            raise ValueError(f"Unsupported completion status: {proposal.status}")

        if task.type not in {"plan_research", "planner_review"} and not proposal.artifacts:
            task.lease = None
            task.status = TaskStatus.BLOCKED
            self.store.update_task(task)
            self.store.append_event(
                "proposal_rejected",
                task_id=task.id,
                reason="completion_missing_artifact",
            )
            self._create_planner_review(task)
            self.store.render_board()
            return

        if proposal.planner_plan is not None:
            if task.type not in {"plan_research", "planner_review"}:
                raise ValueError("Only team-planner tasks may submit a planner plan")
            self._validate_planner_plan(task, proposal.planner_plan)

        artifact_ids = [self.store.write_artifact(task.id, draft) for draft in proposal.artifacts]
        task.output_artifacts.extend(artifact_ids)
        task.lease = None
        task.status = TaskStatus.AWAITING_REVIEW if task.review_required else TaskStatus.COMPLETE
        self.store.update_task(task)
        if proposal.planner_plan is not None:
            materialized = self._materialize_planner_plan(task, proposal.planner_plan)
            self.store.append_event(
                "planner_plan_materialized",
                task_id=task.id,
                created_task_ids=materialized,
                summary=proposal.planner_plan.summary,
            )
        for draft in proposal.follow_up_tasks:
            self._create_follow_up(draft)
        self.store.append_event(
            "proposal_accepted",
            task_id=task.id,
            status=task.status.value,
            artifacts=artifact_ids,
            metrics=proposal.metrics,
        )
        self.refresh_ready_tasks()
        self.store.render_board()

    def approve_task(self, task_id: str) -> None:
        task = self.store.read_task(task_id)
        if task.status is not TaskStatus.AWAITING_REVIEW:
            raise ValueError(f"Task {task_id} is not awaiting review")
        task.status = TaskStatus.COMPLETE
        self.store.update_task(task)
        self.store.append_event("task_approved", task_id=task.id)
        self.refresh_ready_tasks()
        self.store.render_board()

    def expire_leases(self, now: datetime | None = None) -> list[str]:
        now = now or datetime.now(timezone.utc)
        expired: list[str] = []
        for task in self.store.list_tasks():
            if task.status is not TaskStatus.CLAIMED or task.lease is None or task.lease.expires_at > now:
                continue
            expired.append(task.id)
            task.lease = None
            if task.attempt <= 1:
                task.status = TaskStatus.READY
                self.store.append_event("lease_reassigned", task_id=task.id)
            else:
                task.status = TaskStatus.BLOCKED
                self.store.append_event("lease_blocked", task_id=task.id)
                self._create_planner_review(task)
            self.store.update_task(task)
        if expired:
            self.store.render_board()
        return expired

    def record_worker_exit(self, task_id: str, return_code: int, log_path: str | None = None) -> None:
        """Recover immediately when the host observes a worker-process failure."""
        self.store.append_event("worker_exit", task_id=task_id, return_code=return_code, log_path=log_path)
        if return_code == 0:
            return
        task = self.store.read_task(task_id)
        if task.status is not TaskStatus.CLAIMED:
            return
        task.lease = None
        if task.attempt <= 1:
            task.status = TaskStatus.READY
            self.store.update_task(task)
            self.store.append_event("worker_failure_reassigned", task_id=task.id, return_code=return_code)
        else:
            task.status = TaskStatus.BLOCKED
            self.store.update_task(task)
            self.store.append_event("worker_failure_blocked", task_id=task.id, return_code=return_code)
            self._create_planner_review(task)
        self.refresh_ready_tasks()
        self.store.render_board()

    def apply_conflict_verdict(self, conflict_task_id: str, affected_task_ids: list[str]) -> list[str]:
        """Mark only verdict-named dependents stale and create revision work."""
        conflict = self.store.read_task(conflict_task_id)
        if conflict.status is not TaskStatus.COMPLETE:
            raise ValueError("Conflict verdict must be complete before invalidation")
        revisions: list[str] = []
        for task_id in affected_task_ids:
            task = self.store.read_task(task_id)
            if task.status not in (TaskStatus.COMPLETE, TaskStatus.AWAITING_REVIEW):
                continue
            task.status = TaskStatus.STALE
            self.store.update_task(task)
            revision = TaskRecord(
                id=self.store.next_task_id(),
                type="revise_artifact",
                instruction=f"Revise stale output from {task.id} using conflict verdict {conflict_task_id}.",
                required_capabilities=["brief-writing", "task-handoff"],
                input_artifacts=[*task.output_artifacts, *conflict.output_artifacts],
                review_required=task.review_required,
            )
            self.store.create_task(revision)
            revisions.append(revision.id)
            self.store.append_event("task_staled", task_id=task.id, conflict_task_id=conflict_task_id)
        self.refresh_ready_tasks()
        self.store.render_board()
        return revisions

    def _create_follow_up(self, draft: TaskDraft) -> None:
        self.store.create_task(
            TaskRecord(
                id=self.store.next_task_id(),
                type=draft.type,
                instruction=draft.instruction,
                required_capabilities=draft.required_capabilities,
                input_artifacts=draft.input_artifacts,
                review_required=draft.review_required,
            )
        )

    def _create_planner_review(self, task: TaskRecord) -> None:
        self.store.create_task(
            TaskRecord(
                id=self.store.next_task_id(),
                type="planner_review",
                instruction=(
                    f"Re-form and requeue blocked task {task.id}. Original type: {task.type}. "
                    f"Original instruction: {task.instruction}. "
                    f"Original acceptance criteria: {task.acceptance_criteria}."
                ),
                required_capabilities=["task-handoff"],
                input_artifacts=self._merge_artifact_ids(task.input_artifacts, task.output_artifacts),
                review_of_task_id=task.id,
            )
        )
        self.refresh_ready_tasks()

    def _validate_planner_plan(self, planner_task: TaskRecord, plan: PlannerPlan) -> None:
        if len(plan.tasks) > 8:
            raise ValueError("Planner plan exceeds the eight-task fan-out limit")
        keys = [draft.key for draft in plan.tasks]
        if not all(key and key.replace("-", "").replace("_", "").isalnum() for key in keys):
            raise ValueError("Planner task keys must be non-empty alphanumeric slugs")
        if len(keys) != len(set(keys)):
            raise ValueError("Planner plan contains duplicate task keys")
        if planner_task.type == "planner_review":
            if plan.tasks:
                raise ValueError("Planner reviews must re-form the blocked task instead of creating detached tasks")
            if len(plan.reforms) != 1:
                raise ValueError("Planner review must contain exactly one task reform")
            self._validate_task_reform(planner_task, plan.reforms[0])
        elif plan.reforms:
            raise ValueError("Only planner reviews may submit task reforms")
        key_set = set(keys)
        for draft in plan.tasks:
            if draft.type not in PLANNER_TASK_TYPES:
                raise ValueError(f"Unsupported planner task type: {draft.type}")
            if not set(draft.required_capabilities).issubset(PLANNER_CAPABILITIES):
                raise ValueError(f"Unsupported capabilities for planner task {draft.key}")
            if not set(draft.depends_on_keys).issubset(key_set):
                raise ValueError(f"Unknown dependency in planner task {draft.key}")
            if draft.key in draft.depends_on_keys:
                raise ValueError(f"Planner task {draft.key} cannot depend on itself")
            if not set(draft.input_artifacts).issubset(planner_task.input_artifacts):
                raise ValueError(f"Planner task {draft.key} references an unpermitted artifact")
        self._assert_acyclic(plan.tasks)

    def _validate_task_reform(self, planner_task: TaskRecord, reform: TaskReform) -> None:
        if reform.target_task_id != planner_task.review_of_task_id:
            raise ValueError("Planner review may reform only its blocked task")
        if not reform.instruction.strip():
            raise ValueError("Reformed task instruction cannot be empty")
        if not set(reform.required_capabilities).issubset(PLANNER_CAPABILITIES):
            raise ValueError("Reformed task has unsupported capabilities")
        if not set(reform.input_artifacts).issubset(planner_task.input_artifacts):
            raise ValueError("Reformed task references an unpermitted artifact")

    @staticmethod
    def _assert_acyclic(tasks: list[PlannedTaskDraft]) -> None:
        dependencies = {draft.key: set(draft.depends_on_keys) for draft in tasks}
        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(key: str) -> None:
            if key in visiting:
                raise ValueError("Planner plan contains a dependency cycle")
            if key in visited:
                return
            visiting.add(key)
            for dependency in dependencies[key]:
                visit(dependency)
            visiting.remove(key)
            visited.add(key)

        for key in dependencies:
            visit(key)

    def _materialize_planner_plan(self, planner_task: TaskRecord, plan: PlannerPlan) -> list[str]:
        for reform in plan.reforms:
            original = self.store.read_task(reform.target_task_id)
            original.instruction = reform.instruction
            original.required_capabilities = reform.required_capabilities
            original.input_artifacts = self._merge_artifact_ids(original.input_artifacts, reform.input_artifacts)
            original.acceptance_criteria = reform.acceptance_criteria
            original.status = TaskStatus.PENDING
            original.lease = None
            self.store.update_task(original)
            self.store.append_event("task_reformed", task_id=original.id, review_task_id=planner_task.id)
        next_number = len(self.store.list_tasks()) + 1
        task_ids = {draft.key: f"T-{next_number + index:03d}" for index, draft in enumerate(plan.tasks)}
        materialized: list[str] = []
        for draft in plan.tasks:
            task = TaskRecord(
                id=task_ids[draft.key],
                type=draft.type,
                instruction=draft.instruction,
                depends_on=[task_ids[key] for key in draft.depends_on_keys],
                required_capabilities=draft.required_capabilities,
                input_artifacts=draft.input_artifacts,
                review_required=draft.review_required,
                acceptance_criteria=draft.acceptance_criteria,
            )
            self.store.create_task(task)
            materialized.append(task.id)
        return materialized

    @staticmethod
    def _merge_artifact_ids(*groups: list[str]) -> list[str]:
        """Return stable, de-duplicated artifact IDs for a task envelope."""
        return list(dict.fromkeys(artifact_id for group in groups for artifact_id in group))
