# Implementation Focus and Coverage

The assignment brief asks us to choose one or two areas to explore deeply while still
making the rest coherent. The implementation is deepest on orchestration and
handoffs, backed by durable shared state and deliberately bounded context.
Planning/revision and sandboxed execution are also substantial supporting
areas. Recovery is implemented but remains partial until its lifecycle paths
have dedicated tests and a full fixture-run walkthrough.

## Primary deep dive: orchestration and handoffs across agents

Implemented steps:

- A host-local `Runner` claims ready work and starts one short-lived process
  per task, up to a scheduler-owned concurrency cap.
- `Scheduler` is the sole durable-state writer. It controls
  `pending -> ready -> claimed -> awaiting_review/complete` transitions,
  dependency readiness, leases, and board rendering.
- A worker receives a task envelope, writes only an untrusted JSON completion
  proposal to `inbox/`, and exits. The scheduler validates it before writing
  task records or immutable artifacts.
- A capability registry selects the narrowest worker profile and its skills,
  tools, and token/turn budget. The five application skills are task handoff,
  source discovery, evidence extraction, claim assessment, and brief writing.
- The new team lead is a separate, short-lived Strands agent. It proposes a
  bounded DAG with local task keys; the scheduler validates and materializes it
  with real IDs. The lead cannot directly mutate tasks or artifacts.
- When a dependent task becomes ready, the scheduler copies the immutable output
  artifact IDs of its completed dependencies into that task's allowlisted input
  envelope. This makes the DAG edge a concrete, auditable handoff instead of a
  timing-only dependency.

This provides an interview trace from request -> lead plan -> ready task ->
claim -> proposal -> validated artifact -> downstream dependency readiness.
The initial lead-plan path and dependency translation have deterministic tests.

## Primary deep dive: durable shared state and context boundaries

Implemented steps:

- Markdown task records are the inspectable, durable source of truth; `board.md`
  is generated rather than edited concurrently.
- Each worker gets only its task instruction, acceptance criteria, declared
  capabilities, and the IDs of permitted input artifacts—not global history or
  other workers' conversations.
- Durable artifacts are immutable, compact handoff records with an artifact
  kind, summary, structured payload, and input-artifact provenance.
- The only artifact-reading tool checks the task's allowlisted artifact IDs at
  call time. This prevents a broad store search from silently becoming shared
  context.
- Strands `Swarm` is intentionally deferred because its shared handoff context
  would grow with the run. Fresh single-task agents keep contexts bounded.
- A completed conflict verdict can mark only explicitly affected outputs stale
  and create focused revision tasks, rather than reloading or rerunning the
  whole workflow.

## Supporting coverage beyond the two focus areas

### Planning and reasoning, including mid-run revision

Implemented: the team lead returns structured `LeadPlan` data, not free-form
delegation. The scheduler rejects duplicate keys, unknown dependencies, cycles,
unsupported task types/capabilities, excessive fan-out, and unauthorized input
artifacts before materializing a plan. `apply_conflict_verdict` retains prior
evidence, stales only named affected tasks, and queues revision work.

### Self-reflection and recovery from failure

Implemented: claims are leases. The first expired lease or observed process
failure returns work to `ready`; the second blocks it and opens a `lead_review`
task. A semantic contract failure—such as a `complete` response with no required
artifact—goes directly to a bounded review because a blind retry would replay
the malformed envelope. The review receives the failed task's envelope and
allowlisted artifacts, and must submit exactly one validated task reform; the
scheduler requeues that same task with the revised envelope. Review-gated work
uses `awaiting_review` until approved. Workers can also submit a `blocked`
proposal, which triggers the same lead-review path.

Deterministic tests cover immediate process-failure reassignment, second-failure
review, artifact-less completion review, and same-task reform/requeue. A full
subprocess-level fixture walkthrough remains useful presentation evidence but
is not a missing scheduler behavior.

### Tool and execution design, including sandboxed runtimes

Implemented: every fixture or Gemini executor receives a non-root Docker
sandbox. `RestrictedDockerSandbox` disables Strands' automatically vended
generic shell and file-editor tools, so the agent only receives explicit,
task-scoped tools. Web discovery receives bounded `ddg_web_search` and
`web_fetch` tools that run the `ddg-search` and `page-dump` CLIs inside that
sandbox; arXiv discovery retains a read-only MCP tool where its profile permits
it. The host-local runner has no Docker-socket capability.

Current gap: a prepared Docker container and Gemini credential are still needed
for a live end-to-end validation; deterministic tests do not call either.

## Next steps

1. Add citation-grade briefs: persist source metadata and supporting excerpts,
   link claims to citation IDs, and render inline citations plus a bibliography.
   This replaces internal-only references such as `A-004` with a traceable
   `brief claim -> evidence artifact -> source URL/DOI` chain.
2. Evaluate a bounded Strands Swarm for one revision/review task if shared
   scratch context proves valuable.
3. Add provenance-driven invalidation, independent-review policy, and
   production scheduling concerns such as durable queues and quotas.

The supporting features exist to make the two primary deep dives convincing,
not to claim a production-complete orchestration platform.
