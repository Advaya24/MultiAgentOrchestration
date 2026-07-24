# Design Notes

## Depth choices

This project goes deep on durable handoffs and bounded worker context. Markdown
task files and immutable artifacts make each handoff inspectable without a
shared, long-lived agent transcript. A short-lived worker receives only its
task, referenced artifacts, approved tools, and context budget.

## Decisions

- The team lead controls admission, priority, and completion; compatible
  workers pull approved ready work through a scheduler-managed lease.
- Task files are authoritative local state. The scheduler is the sole writer
  for status transitions; `board.md` is a derived view.
- Capability requirements select worker profiles from a registry rather than
  hard-coding a persona per task.
- Evidence, conflict decisions, and final briefs use independent review tasks;
  routine work uses mechanical checks plus lead acceptance.
- Contradictions create conflict-resolution and targeted revision tasks rather
  than rewriting or globally rerunning the workflow.

## Scope cuts and next work

The first version remains single-host and file-backed. It will use deterministic
fixtures for core tests, with Strands and live tools behind narrow worker
boundaries. A production evolution could replace the local scheduler with a
durable queue and database while keeping task and artifact contracts intact.

## Coding tools

Coding assistance was used to inspect the assignment, compare coordination
patterns, draft diagrams and contracts, and verify D2 rendering. Architecture
choices were retained because they directly support the required handoff,
recovery, and bounded-context walkthroughs.
