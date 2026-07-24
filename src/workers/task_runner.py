"""One-task subprocess entrypoint; writes only a completion proposal to inbox."""

from __future__ import annotations

import argparse
import json
import os
import traceback
from datetime import datetime, timezone
from pathlib import Path

from src.agents.sandbox import worker_sandbox
from src.orchestrator.planner import FixturePlannerExecutor, GeminiPlannerExecutor, MistralPlannerExecutor
from src.state.run_store import RunStore
from src.workers.executors import FixtureWorkerExecutor, GeminiWorkerExecutor, MistralWorkerExecutor


def _trace(event: str, **fields: object) -> None:
    """Emit safe lifecycle diagnostics; the runner redirects them to attempt logs."""
    print(
        json.dumps({"at": datetime.now(timezone.utc).isoformat(), "event": event, **fields}, sort_keys=True),
        flush=True,
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--worker-id", required=True)
    parser.add_argument("--mode", choices=("fixture", "gemini", "mistral"), default="fixture")
    parser.add_argument("--sandbox-container", default=os.environ.get("WORKER_SANDBOX_CONTAINER"))
    args = parser.parse_args()

    store = RunStore(Path(args.run_dir))
    task = store.read_task(args.task_id)
    _trace(
        "worker_started",
        task_id=task.id,
        task_type=task.type,
        attempt=task.attempt,
        worker_id=args.worker_id,
        mode=args.mode,
    )
    try:
        if not args.sandbox_container:
            raise RuntimeError("Every executor requires --sandbox-container or WORKER_SANDBOX_CONTAINER.")
        if task.type in {"plan_research", "planner_review"}:
            if args.mode == "fixture":
                executor = FixturePlannerExecutor(
                    sandbox=worker_sandbox(args.sandbox_container)
                )
            elif args.mode == "gemini":
                executor = GeminiPlannerExecutor.from_container(args.sandbox_container)
            else:
                executor = MistralPlannerExecutor.from_container(args.sandbox_container)
        elif args.mode == "fixture":
            executor = FixtureWorkerExecutor(
                sandbox=worker_sandbox(args.sandbox_container)
            )
        elif args.mode == "gemini":
            executor = GeminiWorkerExecutor.from_container(args.sandbox_container)
        else:
            executor = MistralWorkerExecutor.from_container(args.sandbox_container)
        proposal = executor.execute(store, task, Path(args.run_dir).name)
        store.write_proposal(proposal, args.worker_id)
        _trace(
            "proposal_submitted",
            task_id=task.id,
            attempt=task.attempt,
            status=proposal.status,
            artifact_count=len(proposal.artifacts),
            follow_up_count=len(proposal.follow_up_tasks),
        )
    except BaseException as error:
        _trace(
            "worker_failed",
            task_id=task.id,
            attempt=task.attempt,
            error_type=type(error).__name__,
            error_message=str(error),
        )
        traceback.print_exc()
        raise


if __name__ == "__main__":
    main()
