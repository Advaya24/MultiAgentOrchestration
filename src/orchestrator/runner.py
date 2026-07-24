"""Host-local scheduler loop that spawns one short-lived worker process per task."""

from __future__ import annotations

import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import TextIO

from src.orchestrator.scheduler import Scheduler
from src.state.models import TaskRecord, TaskStatus


@dataclass
class Runner:
    """Coordinate subprocess lifecycles without granting workers state authority."""

    scheduler: Scheduler
    mode: str = "fixture"
    sandbox_container: str | None = None
    max_workers: int = 3
    _children: dict[str, subprocess.Popen[bytes]] = field(default_factory=dict, init=False)
    _log_streams: dict[str, TextIO] = field(default_factory=dict, init=False)

    def __post_init__(self) -> None:
        if not self.sandbox_container:
            raise ValueError("Runner requires a Docker sandbox container for every executor.")

    def tick(self) -> None:
        self.scheduler.process_inbox()
        self.scheduler.expire_leases()
        self.scheduler.refresh_ready_tasks()
        self._reap_children()
        capacity = self.max_workers - len(self._children)
        if capacity <= 0:
            return
        ready = sorted(
            (task for task in self.scheduler.store.list_tasks() if task.status is TaskStatus.READY),
            key=lambda task: (-task.priority, task.id),
        )
        for task in ready[:capacity]:
            self._spawn(task)

    def run_until_idle(self, poll_seconds: float = 0.05, max_ticks: int = 72_000) -> None:
        for _ in range(max_ticks):
            self.tick()
            if not self._children and not any(
                task.status in (TaskStatus.READY, TaskStatus.CLAIMED) for task in self.scheduler.store.list_tasks()
            ):
                return
            time.sleep(poll_seconds)
        raise TimeoutError("Runner did not become idle before max_ticks")

    def _spawn(self, task: TaskRecord) -> None:
        worker_id = f"worker-{task.id.lower()}-{task.attempt + 1}"
        claimed = self.scheduler.claim_task(task.id, worker_id)
        command = [
            sys.executable,
            "-m",
            "src.workers.task_runner",
            "--run-dir",
            str(self.scheduler.store.run_dir),
            "--task-id",
            claimed.id,
            "--worker-id",
            worker_id,
            "--mode",
            self.mode,
        ]
        command.extend(("--sandbox-container", self.sandbox_container))
        log_stream = self.scheduler.store.worker_log_path(claimed.id, claimed.attempt).open("w", encoding="utf-8")
        try:
            self._children[claimed.id] = subprocess.Popen(command, stdout=log_stream, stderr=subprocess.STDOUT)
        except Exception:
            log_stream.close()
            raise
        self._log_streams[claimed.id] = log_stream
        self.scheduler.store.append_event(
            "worker_spawned",
            task_id=claimed.id,
            attempt=claimed.attempt,
            worker_id=worker_id,
            log_path=str(self.scheduler.store.worker_log_path(claimed.id, claimed.attempt).relative_to(self.scheduler.store.run_dir)),
        )

    def _reap_children(self) -> None:
        for task_id, process in list(self._children.items()):
            return_code = process.poll()
            if return_code is None:
                continue
            self._log_streams.pop(task_id).close()
            task = self.scheduler.store.read_task(task_id)
            log_path = self.scheduler.store.worker_log_path(task_id, task.attempt).relative_to(
                self.scheduler.store.run_dir
            )
            self.scheduler.record_worker_exit(task_id, return_code, str(log_path))
            del self._children[task_id]
