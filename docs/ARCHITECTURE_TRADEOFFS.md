# Architecture Options and Tradeoffs

## Decision

Version 1 uses a task-board swarm: Markdown task and immutable artifact files,
a single-writer scheduler, a team planner for run-level decisions, and short-lived
Strands workers selected by required capabilities. This optimizes the exercise
for inspectable handoffs, bounded context, deterministic recovery, and a
reproducible local demo rather than maximum distributed throughput.

## Decision criteria

| Criterion | Why it matters here |
| --- | --- |
| Durable handoffs | A worker result must remain useful after the worker exits. |
| Bounded context | Workers should receive a task envelope and referenced artifacts, not a growing transcript. |
| Recovery | Failed or timed-out work must be detectable and safely reassigned. |
| Targeted revision | Contradictory evidence should revise only dependent work. |
| Reproducibility | A reviewer should be able to inspect and replay a local run. |
| Scaling | The design should have a clear path beyond one local process. |

## Options compared

| Option | Strengths | Tradeoffs | Fit for v1 |
| --- | --- | --- | --- |
| **Selected: task-board control plane with short-lived workers** | Durable, inspectable Markdown handoffs; leases and state transitions have one owner; capability-based short-lived workers keep context lean; dependency references support focused revisions. | The scheduler and file contracts are custom code; single-host throughput is limited; the claimed state reduces races only while one scheduler owns claims. | Best overall fit. |
| **Top-level Strands Graph** | Expresses a stable DAG compactly and uses an SDK-native coordination primitive. | A graph alone does not provide durable cross-run leases, artifact provenance, or dependency-driven invalidation; late contradictions require application control logic anyway. | Useful inside a bounded stage later, not as the durable control plane. |
| **Manager-agent delegation** | Natural-language planning and adaptive task decomposition can feel flexible. | Manager context grows; task ownership and retries become prompt-dependent; acceptance decisions are harder to reproduce or audit. | Team planner may use an agent for planning, but scheduler-enforced task state remains authoritative. |
| **Peer/shared-context swarm** | Fast exploratory collaboration and low ceremony for a short conversation. | Shared history grows quickly, mixes irrelevant context into each task, and leaves no reliable boundary for retries or evidence provenance. | Deliberately avoided for durable work. |
| **Event-driven queue-first system** | Strong decoupling, independent scaling, and well-known operational queue semantics. | Requires broker/database setup, event schemas, observability, and idempotent consumers before the core workflow is demonstrated. | Production migration path, excessive for the local exercise. |

## Why the selected model wins

The task board separates coordination from reasoning. The scheduler owns claims,
leases, priority, admission, acceptance, and status transitions; the team planner
only proposes plans or reforms; workers only produce bounded outputs. That makes
a crashed worker recoverable without restoring its conversation, and lets the
system identify which artifact references need revision when evidence changes.

The host-local runner is a deliberately ad hoc choice for this time-boxed
version. It deterministically starts every `ready` task that fits the configured
parallelism budget, rather than relying on an LLM to decide when to spawn. It is
a useful control surface while evaluating the Strands Harness SDK, but it can be
replaced by a harness or durable queue without changing the task/artifact
contracts.

`claimed` is a state transition rather than a distributed mutex. In the current
single scheduler process, a task becomes `claimed` before its subprocess starts,
so the runner will not select it again. Multiple independent schedulers would
need a transactional database or queue claim to obtain the same guarantee.

Markdown is intentionally the v1 durability format: it is easy to review,
diff, and demo. `board.md` is only a generated view, while task files and
immutable artifacts provide the actual handoff record. The file format is an
implementation choice, not a public commitment; the task envelope, artifact
reference, lease, and dependency contracts are the stable boundaries.

## Evolution path

1. Implement the local scheduler and deterministic fixture workers first.
2. Add a small Strands Graph only within fixed sub-workflows where its DAG
   semantics reduce code without taking ownership of durable state.
3. Replace file-backed scheduling with a database and durable queue when
   multiple processes or hosts are required; preserve task IDs, artifact IDs,
   capability requirements, leases, and dependency links.
4. Add tracing, metrics, and stronger idempotency controls as worker count and
   external-tool use increase.

This route retains the benefits of a queue-first architecture at scale without
making broker operations a prerequisite for proving the handoff and recovery
model.
