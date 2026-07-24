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

Durable shared state is the companion choice. In long-horizon work, the
orchestrator's context will eventually compact, so it cannot be the reliable
history of the system. Here that history is stored as Markdown task and artifact
records; in other work I have used an LLM wiki for the same purpose. The
artifact trace lets the scheduler attach an older relevant artifact to a later
or revision task; that worker can then retrieve the named record without
loading the full run history into its context. Workers cannot arbitrarily search
the artifact history.

- **Durable handoffs:** tasks and artifacts survive worker exits, retries, and
  later revision. This is the layer that keeps a multi-step run coherent rather
  than treating it as one long agent conversation.
- **Bounded context:** each worker receives only its task contract and
  allowlisted input artifacts. That keeps retries cheap and prevents unrelated
  history from silently becoming evidence.

Planning/revision, recovery, sandboxing, and observability support those two
choices rather than trying to be separate broad areas of depth.

## Decisions I am most confident about

- **A task queue with parallel workers and an explicit dependency graph:** the
  scheduler starts every ready task that fits the parallelism budget, while the
  graph makes sequencing and handoffs visible. This is similar to the task-list
  and parallel-execution patterns I find useful in Claude Code and Superpowers:
  independent work can proceed at once, while dependent work waits for the
  right inputs.
- **Durable artifacts instead of a shared conversation:** workers receive only
  their task contract and named upstream artifacts. The scheduler, rather than
  an agent's temporary context, keeps the durable history. This makes retries
  and later revisions easier to reason about, and avoids unrelated context
  silently becoming evidence.
- **Full observability despite the short time limit:** task events, worker
  logs, traces, a graph, and a small dashboard made live failures much easier
  to debug. This was relatively inexpensive to add and made the system easier
  to inspect than a black-box multi-agent run.
- **An orchestrator-style pattern with tighter context management:** the lead
  plans dependency-aware work and the scheduler controls execution and durable
  state. I think this should work well for medium-horizon, decomposable tasks.
  I am less confident about 100-plus-step workflows until the lead can inspect
  compact run summaries and perform the final goal-level verification described
  below.

## Scope cuts and what I would build next

- **Goal-level verification:** this is the first feature I would add. Today,
  the run stops when every planned task is finished; it does not prove that the
  final brief answers the original request. Add a final lead or reviewer task
  that receives the original request, a compact task-status summary, and
  read-only access to the final brief and supporting artifacts. It must either
  accept the result, create narrowly scoped revision tasks, or mark the run
  blocked. Limit review cycles so a run cannot loop forever. A coding-agent
  hallucination caused this feature to be missed: it assumed that exhausting
  the task graph verified the original goal. I discovered the omission during
  code review and while taking these notes. The original intent was an
  orchestrator-style lead agent that verified previous steps before accepting
  the final result.
- **Dynamic skill discovery:** remove the fixed worker profiles and let an
  agent inspect a skill catalog, choose the skills that fit its assigned task,
  and record that choice in the task
  handoff. Keep simple task-level limits and an allowlist for sensitive tools,
  but do not require a code change just to support a new combination of skills.
- **Citation-grade briefs:** persist source metadata and exact supporting
  excerpts, link claims to citation IDs, and render inline citations plus a
  bibliography linked to original URLs or DOIs. The current brief can still
  expose only an internal artifact ID.
- **Provenance-driven invalidation:** use those claim-to-source links to find
  the exact claims and brief sections affected by a later conflict verdict.
- **Operational scale:** retain the task/artifact contracts but replace the
  single-host Markdown/polling runner with transactional claims in a durable
  queue and database. Add per-run token/cost budgets at the same time.
