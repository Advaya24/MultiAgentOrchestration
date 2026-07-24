# Strands Implementation Contract

## Boundary of responsibility

The application owns durable orchestration. The scheduler is the sole writer
of Markdown task state, leases work, validates transitions, and creates
recovery or revision work. Strands provides the reasoning and tool loop inside
short-lived workers; conversation history is never workflow state.

Version 1 does not use the built-in Strands `Swarm`: its shared handoff context
would grow with the run. A later revision worker may use a tightly bounded
swarm for one conflict or brief-review task. A Strands `Graph` is likewise
reserved for fixed sub-workflows.

## Runtime boundary and sandboxing

The runner is one host-local scheduler process. It owns the durable run
directory and deliberately does not receive Docker-socket privileges. Each
claimed task starts one short-lived worker subprocess, which creates one fresh
Strands agent and exits after submitting its result.

Every worker executor receives a Strands `DockerSandbox`. The sandbox container
runs as a non-root `worker` user with a task workspace. A local
`RestrictedDockerSandbox` disables the SDK's auto-vended generic Bash and
file-editor tools: the sandbox is an execution boundary for sandbox-aware
skills and future tools, while the capability registry exposes only explicit
task tools.

Build and start the local sandbox before any fixture, Gemini, or Mistral run:

```sh
docker build -f docker/worker-sandbox.Dockerfile -t moa-worker-sandbox:local .
docker run -d --rm --name moa-worker-sandbox moa-worker-sandbox:local
export WORKER_SANDBOX_CONTAINER=moa-worker-sandbox
```

The image creates `/workspace` and runs as the non-root `worker` user, matching
the `DockerSandbox` configuration. Stop the ephemeral container with
`docker rm -f moa-worker-sandbox` after local work.

Workers can read only the artifact IDs named by their task envelope. They write
only untrusted completion proposals under `inbox/`; the scheduler validates
proposals before it writes task files, immutable artifacts, events, or the
generated board.

## Worker contract

Capability requirements resolve through a registry to a persona, application
skill directories, explicit tool allowlist, and token/turn budgets. Strands'
`AgentSkills` plugin progressively loads instructions, but its `allowed_tools`
metadata is not a permission boundary. The registry constructs the actual
`Agent(tools=...)` list and every tool validates its task and artifact scope.

`CompletionProposal` contains a status, compact handoff summary, artifact
drafts, and optional follow-up task drafts. The scheduler performs mechanical
validation and sends high-risk outputs to independent review before acceptance.
Every completed non-lead task must include at least one artifact draft; an
artifact-less completion is blocked and routed to lead review instead of
silently becoming a broken downstream handoff.

## Team-lead contract

The team lead is a separate, short-lived Strands agent invoked only for
`plan_research` and `lead_review` tasks. It has no application tools, no
filesystem tools, and no authority to call scheduler methods. Its sole output
is a structured plan: a compact rationale plus a bounded set of typed task
drafts. Each draft has a stable local key, an allowed task type, required
capabilities from the five application skills, acceptance criteria, and local
dependency keys.

The scheduler validates and materializes that plan. It rejects duplicate keys,
unknown dependencies, dependency cycles, unsupported task types or
capabilities, excessive fan-out, and input-artifact references not permitted
by the lead task. It then assigns real task IDs, translates local dependency
keys, persists the tasks, and records a `lead_plan_materialized` event. Thus a
model can propose work but cannot create, complete, re-prioritize, or cancel
durable tasks directly.

Fixture, Gemini, and Mistral leads share this contract. The fixture lead deterministically
creates parallel discovery tasks, so lifecycle tests do not need a model or
Docker daemon. The live lead receives a Docker sandbox for implementation
uniformity, though it is deliberately given no generic sandbox tools. It uses
a fresh `Agent` with bounded turns/tokens and structured output; its prompt is
limited to the lead task, permitted input artifact IDs, and the task catalog.

## Model providers and source provenance

Live workers and the team lead default to `gemini-3.5-flash-lite` through
`GeminiModel`; `GEMINI_MODEL` remains a local override. Web-discovery workers
receive two explicit Python tools: `ddg_web_search` and `web_fetch`. They invoke
the
[`ddg-search`](https://github.com/Djarvur/ddg-search) CLI inside the existing
non-root Docker sandbox: the former has a bounded result count, timeout,
safe-search, and shell-quoted query; the latter uses the bundled `page-dump`
binary for an allowlisted `http`/`https` URL, bounded timeout, and capped
Markdown response. They have no API key and do not grant a general shell or
unbounded web-fetching capability. arXiv discovery workers retain the separate
read-only arXiv MCP client. Discovery must output title, URL, snippet,
rationale, and source-family records. Retrieved content—not a search snippet—
is required before it supports evidence or claims.

Live workers use permissive execution budgets: up to 64 model turns and a
64,000-token cumulative budget per task. The lead receives 16 turns and a
16,000-token cumulative budget. These limits leave room for multi-step
retrieval and structured handoff while retaining an eventual hard stop. The
host runner allows a one-hour idle window for a full live DAG; individual tool
timeouts remain much shorter.

`FixtureWorkerExecutor` produces deterministic artifacts, failures, and
contradictions for harness tests. `GeminiWorkerExecutor` implements the same
completion interface, so scheduler behavior has one code path in both modes.
Pass `--mode mistral` to use `MistralModel` instead, authenticated by
`MISTRAL_API_KEY` and optionally configured with `MISTRAL_MODEL` (default:
`mistral-small-2506`). Gemini remains available through `--mode gemini`.

## Operational limits and acceptance

The scheduler owns the concurrent-worker cap. Each live model invocation receives
per-task turn/token limits and run/task trace attributes. Live Gemini mode
requires a running Docker daemon, a prepared sandbox container named by
`WORKER_SANDBOX_CONTAINER` (or `--sandbox-container`), and `GEMINI_API_KEY`.
Compact lifecycle and metric events go to `events.md`; raw prompts,
conversation history, and credentials do not persist.

Each worker attempt also has a host-captured log at
`logs/<task-id>-attempt-<n>.log`. The runner redirects worker stdout and stderr
there from process start, then records the relative log path and exit code in
the corresponding `worker_exit` event. This preserves Python tracebacks,
provider warnings, and tool diagnostics needed to investigate a failed attempt
without persisting prompts or credentials. Successful proposal events retain
safe executor metadata such as the model stop reason and trace attributes link
events to the run/task IDs.

The task-runner additionally emits newline-delimited JSON lifecycle records to
that log: `worker_started`, `proposal_submitted`, or `worker_failed`. Failure
records include the exception class, sanitized message, and Python traceback.
This is host-visible observability, not model chain-of-thought capture; raw
prompts, credentials, and opaque model reasoning remain excluded.

Live Strands agents add callback events to the same attempt log. These record
model-stream and tool-call lifecycle payloads, timestamps, run/task IDs, and
safe output data. The callback recursively redacts credential-shaped fields and
excludes `reasoningText`; the latter is not a reliable or appropriate durable
trace. This makes the agent's observable execution inspectable alongside its
host process and scheduler lifecycle.

Each fresh executor also configures Strands' native OpenTelemetry tracer with a
local standard `ConsoleSpanExporter` at `traces/<task-id>-attempt-<n>.otel.json`.
It retains
the hierarchical agent, cycle, model-invocation, and tool-invocation spans with
timestamps, IDs, token/latency attributes, and captured request/response or
tool-result attributes. It omits hidden reasoning fields. When
`OTEL_EXPORTER_OTLP_ENDPOINT` is configured, the same standard StrandsTelemetry
setup also exports to that OTLP collector without changing agent code.

Every scheduler event is also appended as one JSON object to `trace.jsonl`.
Together, `trace.jsonl`, `events.md`, per-attempt logs, task records, and
artifacts provide a traceable chain for both successful and failed work:
spawn -> start -> proposal or failure -> process exit -> scheduler decision.

The CLI creates each normal run under the repository's ignored `runs/`
directory, using an `America/Los_Angeles` (Pacific Time) timestamp with
microseconds to avoid name collisions. `--run-dir` remains available for an
explicit reproducible path.

Every scheduler board refresh also derives a live task graph from the durable
task records. `task_graph.d2` is an editable D2 source, `task_graph.svg` is its
atomically rendered visualization, and `task_graph.md` contains the equivalent
Mermaid graph for Markdown renderers. The host needs the `d2` CLI available.
The scheduler refreshes these derived views after every lifecycle event. All
show task ID, type, status, and attempt, with dependency edges; none is an
authority for orchestration state.

Every board refresh also derives `metrics.json`, `stats.md`, and a matplotlib
`stats.png` from the native local OTel model-invocation spans. The PNG provides
an embedded bar visualization of tokens and latency per request; the Markdown and JSON
provide the values. Together they include per-request and aggregate input,
output, and total tokens; end-to-end invocation latency; and model-provided
time-to-first-token when available. The raw spans remain the authority. A
derived `report.md` exposes the latest `research_brief` payload as normal
Markdown, while the immutable artifact remains the durable handoff record.

The runner reports a nonzero worker-process exit to the scheduler immediately:
the scheduler releases the lease and reassigns the first failed attempt without
waiting for its timeout. A second failure blocks the task and opens lead review.
Lease expiry remains the fallback for a hung or disconnected worker whose
process exit is not observable. Conflicting evidence remains immutable, opens a
conflict task, and only its verdict marks affected outputs stale and queues
focused revisions.
