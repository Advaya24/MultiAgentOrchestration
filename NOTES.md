# Design Notes

## Depth choices

This project goes deep on durable handoffs and bounded worker context. Markdown
task files and immutable artifacts make each handoff inspectable without a
shared, long-lived agent transcript. A short-lived worker receives only its
task, referenced artifacts, approved tools, and context budget.

## Decisions

- The team lead proposes bounded plans and task reforms; the scheduler controls
  admission, priority, claims, completion, and every durable state transition.
- Task files are authoritative local state. The scheduler is the sole writer
  for status transitions; `board.md` is a derived view.
- Capability requirements select worker profiles from a registry rather than
  hard-coding a persona per task.
- Tasks use mechanical scheduler validation by default; explicitly
  review-required tasks pause for approval. The lead never accepts work.
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
