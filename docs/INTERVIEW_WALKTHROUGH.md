# Interview Walkthrough

This is a concise, evidence-backed route through the two deep-focus areas:
durable handoffs and bounded worker context. Use a completed `runs/run-*`
directory while walking through it.

## 1. One unit of work, end to end

Start with `T-002` (`discover_sources`) in `tasks/T-002.md`.

1. `Runner.tick()` sees it as `ready`, claims it with a 300-second lease, and
   starts one short-lived `src.workers.task_runner` subprocess. The transition
   appears in `events.md` as `task_claimed` and `worker_spawned`.
2. The subprocess builds the narrow `web_discovery` profile and executes one
   fresh Strands agent. It can use only the task-handoff and source-discovery
   skills, the allowed-artifact reader, and bounded sandboxed web tools.
3. It writes an untrusted `CompletionProposal` to `inbox/` and exits. The
   scheduler validates the proposal, writes immutable `artifacts/A-001.md`,
   marks `T-002` complete, and records `proposal_accepted`.
4. The downstream `T-003` becomes ready; the scheduler copies `A-001` into its
   `input_artifacts` allowlist. The exact handoff is visible in `T-003.md` and
   its `task_ready` event.

Cost is explicit, not hidden in a shared chat: one worker subprocess and one
or more model invocations. `stats.md`, `stats.png`, and `metrics.json` derive
per-request input/output/total tokens and invocation latency from raw OTel
spans in `traces/`. The current permissive guardrails are 64 worker turns and
64,000 cumulative worker tokens; the lead has 16 turns and 16,000 tokens.

## 2. What a worker receives—and deliberately does not

`task_runner.py` reads one `TaskRecord`; `build_worker_agent()` constructs the
agent from that record. The task envelope contains:

- task ID, type, instruction, acceptance criteria, and attempt;
- only the declared input artifact IDs;
- the profile selected from required capabilities.

It does not receive other task records, the global board, other agents'
messages, arbitrary artifact search, a generic shell, host filesystem access,
or Docker-socket access. `read_allowed_artifact` checks the allowlist at call
time; `RestrictedDockerSandbox` suppresses Strands' generic shell/editor tools.
The rationale is to make retries cheap and prevent global history from growing
each worker's context window.

## 3. The handoff and its staleness bound

Artifacts are immutable Markdown records. A dependent task remains `pending`
until every durable dependency is `complete`. In `refresh_ready_tasks()`, the
scheduler reads dependency output artifact IDs, stable-deduplicates them into
the dependent task's `input_artifacts`, persists the task, then makes it
`ready`.

Therefore B cannot run with a stale pre-handoff view: it observes the artifact
set committed at the state transition. It can become semantically stale only
after a later conflict verdict; that is handled separately below. There is no
eventual-consistency cache between the task files and scheduler in this
single-host design.

## 4. Kill a worker mid-step

Kill the task subprocess. On the next runner tick, `_reap_children()` observes
a nonzero exit and calls `Scheduler.record_worker_exit()` immediately. The
worker's stdout/stderr, lifecycle JSON, and Python traceback remain in
`logs/<task>-attempt-<n>.log`; `events.md` links that log path.

- First observed process failure: release the lease and return the same task to
  `ready` for one ordinary retry.
- Second observed process failure: mark it `blocked` and create a `lead_review`.
- If process observation is unavailable: the 300-second lease expiry is the
  fallback, with the same first-retry/second-review policy.

The cost is one repeat task attempt. A semantic failure is handled differently:
a `complete` proposal without a required artifact is immediately blocked,
because blindly retrying the same malformed task envelope would not help. Its
lead review carries the failed task's envelope and must issue exactly one
validated `TaskReform` that requeues that same task.

## 5. A late contradiction invalidates earlier work

An accepted conflict verdict invokes `apply_conflict_verdict(conflict_task_id,
affected_task_ids)`. The verdict names the affected completed artifacts; the
scheduler marks only their producing tasks `stale` and creates one
`revise_artifact` task per affected output. Each revision receives the old
artifact and conflict verdict IDs as inputs.

The cost to find taint is proportional to the explicitly named affected task
IDs, not to the entire run. The present system deliberately does not infer the
affected set automatically; a reviewer or conflict worker must make that
judgment. This is a current limitation, not hidden automation.

## 6. What breaks first as horizon grows

The first limits are single-host polling, Markdown-file coordination, bounded
but local subprocess supervision, and manual conflict-target selection. The
next build would keep the task/artifact contract but replace the local runner
with a durable queue plus database-backed transactional claims and provenance
edges. Next would be automated impact analysis over those edges, per-run token
budgets/quotas, and a bounded revision-only Swarm only where shared scratch
context demonstrably improves a review task.

## Next steps

1. Add citation-grade briefs. Discovery would save source metadata and
   supporting excerpts; assessment would link claims to citation IDs; the final
   brief would render inline citations and a bibliography. This gives every
   material claim a chain back to its source URL or DOI, rather than only to an
   internal artifact ID.
2. Use those provenance links to identify affected claims automatically when a
   conflict verdict arrives.
3. Add per-run token and cost budgets after the permissive live-run limits have
   served their debugging purpose.

## Evidence to open during the interview

- `board.md` and `task_graph.svg`: current DAG and state.
- `events.md` and `trace.jsonl`: scheduler decisions in chronological form.
- `tasks/` and `artifacts/`: authoritative envelopes and immutable handoffs.
- `logs/`: worker lifecycle, tool events, traceback, and process exit evidence.
- `traces/*.otel.json`, `stats.md`, `stats.png`, and `metrics.json`: raw and
  summarized model-request cost and latency evidence.
- `report.md`: rendered final brief; the underlying brief remains immutable in
  `artifacts/`.
