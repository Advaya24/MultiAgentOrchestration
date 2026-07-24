# Repository Guidelines

## Project Structure & Module Organization

This repository is an early scaffold for the multi-agent orchestration exercise. Keep the repository root limited to project documentation and configuration:

- `README.md`: runnable setup, chosen goal, and architecture sketch.
- `.local/Specs.md`: local assignment constraints and evaluation criteria; treat it as the product brief, but do not submit it.
- `NOTES.md`: design tradeoffs, scope cuts, and future work (add when implementation starts).

`.local/Specs.md` is intentionally local and ignored. Do not stage, commit, or change its ignore/tracking status without the user's explicit approval. More generally, do not alter `.gitignore` rules that change a file's tracking visibility without explicit approval.

Place application code in `src/`, grouped by responsibility (for example, `src/agents/`, `src/orchestrator/`, `src/workers/`, and `src/state/`). Put optional standalone demonstrations in `examples/`. Local operator helpers belong in `.local/scripts/`, not the submission surface. Put tests in `tests/`, mirroring source modules, and use `artifacts/` or `logs/` only for reproducible generated run output. Do not commit secrets, virtual environments, caches, or local databases.

## Build, Test, and Development Commands

No dependency manifest or automated commands are configured yet. When adding the Python implementation, document the authoritative commands in `README.md` and keep them reproducible. The expected local workflow should resemble:

```sh
python -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
pytest
```

Use `python -m ...` so the active virtual environment is unambiguous. If a formatter, linter, or task runner is introduced, expose it through a checked-in configuration and document its command.

## Work Logging

Record material implementation actions, decisions, assumptions, and verification results in the local work log with `sh .local/scripts/log_work.sh`. Use a concise, outcome-oriented entry before ending a work session and after meaningful changes in direction, such as selecting an architecture, diagnosing a failure, changing a recovery strategy, or completing a test run.

```sh
sh .local/scripts/log_work.sh "Decision: use versioned evidence records for agent handoffs"
```

The script writes to `.local/work-log.md`; treat it as local operational history. Do not commit it, and never put secrets, credentials, private data, or large raw tool output in it. Keep reproducible runtime logs in `logs/` only when they are useful project artifacts, and sanitize them before sharing.

## Coding Style & Naming Conventions

Target Python 3, use four-space indentation, type hints for public interfaces, and clear module docstrings where behavior is non-obvious. Use `snake_case` for files, functions, and variables; `PascalCase` for classes; and `UPPER_SNAKE_CASE` for constants. Prefer small, explicit data models for work items, handoffs, and persisted state. Keep runtime-boundary payloads serializable and versioned.

## Testing Guidelines

Use `pytest`; name test files `test_<module>.py` and tests `test_<behavior>()`. Cover success, timeout/failure, retry, and stale-context paths, especially around agent handoffs and state recovery. Mock external model or network calls so the suite remains deterministic. Add a regression test with every behavioral fix.

## Commit & Pull Request Guidelines

Existing history uses short imperative subjects (for example, `Initial commit`); continue with concise, action-oriented messages such as `Add durable handoff store`. Keep commits focused. Pull requests should state the goal, architecture impact, commands run, and known limitations; link the relevant issue when one exists. Include sanitized logs or screenshots for observable workflow changes, never credentials or private run data.
