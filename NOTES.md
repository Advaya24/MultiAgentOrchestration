# Notes

## Where I went deep and why

I chose the research-brief problem partly because it makes the orchestration
problem concrete: discovery, extraction, assessment, and writing naturally
contain both parallel and dependent work. I have been working on orchestration
and handoffs in different forms for more than six months, and this is the part
of agent systems I find most interesting. As horizons grow, one agent is
unlikely to handle every step well—even with strong context management—because
some work should be parallelized and later reconciled.

I therefore focused on durable orchestration/handoffs and bounded worker
context.

- **Durable handoffs:** tasks and artifacts survive worker exits, retries, and
  later revision. This is the layer that keeps a multi-step run coherent rather
  than treating it as one long agent conversation.
- **Bounded context:** each worker receives only its task contract and
  allowlisted input artifacts. That keeps retries cheap and prevents unrelated
  history from silently becoming evidence.

Planning/revision, recovery, sandboxing, and observability support those two
choices rather than trying to be separate broad areas of depth.

## Decisions I am most confident about

- The scheduler is the only durable-state writer. The lead can propose a plan;
  workers can propose results; neither can directly mutate task state.
- Markdown tasks and immutable artifacts are the local source of truth. The
  board, graph, dashboard, and rendered report are derived views.
- Dependency completion creates the handoff: the scheduler copies completed
  upstream artifact IDs into the downstream worker's allowlist before it can
  run.
- Fresh, capability-selected workers are preferable here to a long-lived shared
  Swarm. The built-in Swarm is deferred to a narrowly scoped revision task if
  shared scratch context proves valuable.
- Docker sandboxing is applied to workers and their explicit tools, while the
  host runner stays outside the sandbox and has no Docker-socket authority.
- Standard OpenTelemetry plus raw local spans, worker logs, a task graph, and a
  small stats dashboard make a run inspectable without inventing a custom
  tracing protocol.

## Scope cuts and what I would build next

- **Citation-grade briefs:** persist source metadata and exact supporting
  excerpts, link claims to citation IDs, and render inline citations plus a
  bibliography linked to original URLs or DOIs. This is the immediate next
  product step because the current brief can still expose only an internal
  artifact ID.
- **Provenance-driven invalidation:** use those claim-to-source links to find
  the exact claims and brief sections affected by a later conflict verdict.
- **Operational scale:** retain the task/artifact contracts but replace the
  single-host Markdown/polling runner with transactional claims in a durable
  queue and database. Add per-run token/cost budgets at the same time.

## Coding tools

I used coding assistance to explore coordination options, draft and revise the
architecture and D2 diagrams, implement the scheduler/worker contracts, inspect
live traces, diagnose failures, and add regression tests. The final decisions
were kept only when they supported the two focus areas above; generated run
data, local credentials, assignment materials, and operational notes remain
outside the submitted repository.
