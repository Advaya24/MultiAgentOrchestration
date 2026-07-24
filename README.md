# MultiAgentOrchestration

## Setup and verification

Python 3.10 or newer is required. Create an isolated environment and install
the project with its development dependencies:

```sh
python -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
python -m pytest
```

Every executor, including deterministic fixture executors, requires a running
Docker daemon and a prepared sandbox container supplied through
`WORKER_SANDBOX_CONTAINER`. Live Gemini mode requires a local `GEMINI_API_KEY`;
live Mistral mode requires `MISTRAL_API_KEY`. Fixture mode does not call a model
or external research tools.
The image includes the `ddg-search` and `page-dump` CLIs used by the explicit,
sandboxed web-discovery and web-fetch tools; they need no search API key.

Prepare the local worker sandbox once per development session:

```sh
docker build -f docker/worker-sandbox.Dockerfile -t moa-worker-sandbox:local .
docker run -d --rm --name moa-worker-sandbox moa-worker-sandbox:local
export WORKER_SANDBOX_CONTAINER=moa-worker-sandbox
```

## View Strands traces in Jaeger

Start local Jaeger. Set standard OTLP endpoint in shell that runs task board:

```sh
docker compose up -d jaeger
export OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318
export OTEL_SERVICE_NAME=multi-agent-orchestration
```

Run either live task-board command below. Open http://localhost:16686. Select
`multi-agent-orchestration`, then inspect trace. Per-attempt JSONL span files
remain under `runs/<run-id>/traces/`. Jaeger receives native hierarchical
Strands spans only when `OTEL_EXPORTER_OTLP_ENDPOINT` set and persists its
indexed trace store under `runs/jaeger/` for local run history.

```sh
docker compose down
```

## Run the task board

Run output defaults to a new untracked, timestamped directory under `runs/`.
Pass `--run-dir` only when you need a specific location.

```sh
.venv/bin/python -m src.cli run --request-file request.md --mode gemini
.venv/bin/python -m src.cli run --request-file request.md --mode mistral
.venv/bin/python -m src.cli inspect --run-dir runs/run-YYYYMMDDTHHMMSSffffffPT
```

Each run folder contains `board.md`, `task_graph.d2`, rendered
`task_graph.svg`, `task_graph.md`, `tasks/`, `artifacts/`, `inbox/`, `logs/`,
`events.md`, and `trace.jsonl`. Install the `d2` CLI before running the
scheduler so it can render the SVG. Each worker attempt's stdout/stderr is in
`logs/`; its exit event points to the corresponding log, while `trace.jsonl`
mirrors every scheduler event in machine-readable form. The CLI prints the
created run directory before the final board. Native Strands agent spans are
stored per attempt under `traces/*.otel.json`. Matplotlib renders `stats.png`,
embedded by `stats.md`, to visualize tokens and latency per model request;
`metrics.json`
retains the underlying structured values, including time-to-first-token.
`report.md` is a rendered view of the
latest `research_brief` artifact, so it can be opened directly without reading
YAML payload metadata.

## Optional standalone example

With `GEMINI_API_KEY` in a local `.env` file, run:

```sh
.venv/bin/python -m examples.base_agent "Explain agent handoffs in two sentences."
.venv/bin/python -m examples.base_agent --provider mistral "Explain agent handoffs in two sentences."
```

This optional single-agent example is deliberately outside `src/`; it is not
used by the task-board system. It has one read-only arXiv MCP tool, launched by
`uvx` on demand. The task board itself uses `--mode gemini` or `--mode mistral`.

## Project documents

- [Research brief use case](docs/USE_CASE.md)
- [Task-board swarm architecture](docs/ARCHITECTURE.md)
- [Architecture options and tradeoffs](docs/ARCHITECTURE_TRADEOFFS.md)
- [Strands implementation contract](docs/STRANDS_IMPLEMENTATION.md)
- [Selected engineering focus](docs/IMPLEMENTATION_FOCUS.md)
- [Interview walkthrough](docs/INTERVIEW_WALKTHROUGH.md)
- [Strands Harness SDK reference](docs/STRANDS_HARNESS.md)
- [Gemini integration reference](docs/GEMINI_INTEGRATION.md)
- [Design notes](NOTES.md)
