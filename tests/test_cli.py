"""CLI defaults for local, inspectable task-board runs."""

from __future__ import annotations

from datetime import datetime, timezone

from src.cli import REPOSITORY_ROOT, default_run_dir


def test_default_run_dir_is_under_ignored_repository_runs_directory() -> None:
    run_dir = default_run_dir(datetime(2026, 7, 23, 12, 34, 56, 123456, tzinfo=timezone.utc))

    assert run_dir == REPOSITORY_ROOT / "runs" / "run-20260723T053456123456PT"
