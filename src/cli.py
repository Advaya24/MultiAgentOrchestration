"""Command-line entrypoint for deterministic task-board runs."""

from __future__ import annotations

import argparse
import os
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from src.orchestrator.runner import Runner
from src.orchestrator.scheduler import Scheduler
from src.state.models import TaskRecord
from src.state.run_store import RunStore


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
PACIFIC_TIME = ZoneInfo("America/Los_Angeles")


def default_run_dir(now: datetime | None = None) -> Path:
    """Return a unique, ignored run directory beneath the repository root."""
    timestamp = (now or datetime.now(PACIFIC_TIME)).astimezone(PACIFIC_TIME).strftime("%Y%m%dT%H%M%S%fPT")
    return REPOSITORY_ROOT / "runs" / f"run-{timestamp}"


def main() -> None:
    parser = argparse.ArgumentParser(prog="multi-agent-orchestration")
    subparsers = parser.add_subparsers(dest="command", required=True)
    run_parser = subparsers.add_parser("run")
    run_parser.add_argument("--request-file", required=True)
    run_parser.add_argument("--run-dir")
    run_parser.add_argument("--mode", choices=("fixture", "gemini", "mistral"), default="fixture")
    run_parser.add_argument("--max-workers", type=int, default=3)
    run_parser.add_argument("--sandbox-container", default=os.environ.get("WORKER_SANDBOX_CONTAINER"))
    inspect_parser = subparsers.add_parser("inspect")
    inspect_parser.add_argument("--run-dir", required=True)
    args = parser.parse_args()

    if args.command == "inspect":
        print((Path(args.run_dir) / "board.md").read_text(encoding="utf-8"))
        return

    request = Path(args.request_file).read_text(encoding="utf-8").strip()
    run_dir = Path(args.run_dir) if args.run_dir else default_run_dir()
    store = RunStore(run_dir)
    scheduler = Scheduler(store)
    initial = TaskRecord(
        id=store.next_task_id(),
        type="plan_research",
        instruction=request,
        required_capabilities=["task-handoff"],
    )
    scheduler.create_task(initial)
    Runner(
        scheduler=scheduler,
        mode=args.mode,
        sandbox_container=args.sandbox_container,
        max_workers=args.max_workers,
    ).run_until_idle()
    print(f"Run directory: {store.run_dir}")
    print((store.run_dir / "board.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()
