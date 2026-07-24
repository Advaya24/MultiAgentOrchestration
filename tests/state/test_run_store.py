"""Derived task-board visualizations."""

from __future__ import annotations

from src.state.models import ArtifactDraft, TaskRecord
from src.state.run_store import RunStore


def test_render_board_creates_live_task_graphs(tmp_path) -> None:
    store = RunStore(tmp_path / "run")
    store.create_task(TaskRecord(id="T-001", type="discover_sources", instruction="Discover sources."))
    store.create_task(
        TaskRecord(
            id="T-002",
            type="extract_evidence",
            instruction="Extract evidence.",
            depends_on=["T-001"],
        )
    )

    store.render_board()

    d2 = (store.run_dir / "task_graph.d2").read_text(encoding="utf-8")
    mermaid = (store.run_dir / "task_graph.md").read_text(encoding="utf-8")
    assert "task_T_001 -> task_T_002" in d2
    assert "task_T_001 --> task_T_002" in mermaid
    assert "discover_sources" in d2
    assert "<svg" in (store.run_dir / "task_graph.svg").read_text(encoding="utf-8")


def test_append_event_refreshes_live_task_graph(tmp_path) -> None:
    store = RunStore(tmp_path / "run")
    store.create_task(TaskRecord(id="T-001", type="discover_sources", instruction="Discover sources."))
    store.append_event("task_created", task_id="T-001")

    graph = (store.run_dir / "task_graph.d2").read_text(encoding="utf-8")
    assert "task_T_001" in graph
    trace = (store.run_dir / "trace.jsonl").read_text(encoding="utf-8")
    assert '"event": "task_created"' in trace


def test_worker_log_path_is_attempt_scoped(tmp_path) -> None:
    store = RunStore(tmp_path / "run")

    assert store.worker_log_path("T-001", 2) == store.run_dir / "logs" / "t-001-attempt-2.log"
    assert store.otel_trace_path("T-001", 2) == store.run_dir / "traces" / "t-001-attempt-2.otel.json"


def test_render_dashboard_summarizes_otel_requests_and_renders_brief(tmp_path) -> None:
    store = RunStore(tmp_path / "run")
    store.otel_trace_path("T-001", 1).write_text(
        '''{
  "name": "chat",
  "start_time": "2026-07-24T04:22:10Z",
  "end_time": "2026-07-24T04:22:12Z",
  "attributes": {
    "task.id": "T-001",
    "profile": "writer",
    "gen_ai.request.model": "test-model",
    "gen_ai.usage.input_tokens": 10,
    "gen_ai.usage.output_tokens": 5,
    "gen_ai.usage.total_tokens": 15,
    "gen_ai.server.time_to_first_token": 400
  }
}
{
  "name": "invoke_agent Strands Agents",
  "start_time": "2026-07-24T04:22:10Z",
  "end_time": "2026-07-24T04:22:12Z",
  "attributes": {
    "task.id": "T-001",
    "profile": "writer",
    "gen_ai.request.model": "test-model",
    "gen_ai.usage.input_tokens": 10,
    "gen_ai.usage.output_tokens": 5,
    "gen_ai.usage.total_tokens": 15
  }
}
''',
        encoding="utf-8",
    )
    store.write_artifact(
        "T-001",
        ArtifactDraft(kind="research_brief", summary="Brief.", payload={"brief_text": "# Rendered brief\n\nBody."}),
    )

    store.render_dashboard()

    metrics = (store.run_dir / "metrics.json").read_text(encoding="utf-8")
    assert '"request_count": 1' in metrics
    assert '"total_tokens": 15' in metrics
    assert '"latency_ms": 2000.0' in metrics
    assert "| T-001 | writer | test-model | 10 | 5 | 15 | 2000.0 |" in (store.run_dir / "stats.md").read_text()
    chart = (store.run_dir / "stats.png").read_bytes()
    assert chart.startswith(b"\x89PNG\r\n\x1a\n")
    assert "![Token and latency by model request](stats.png)" in (store.run_dir / "stats.md").read_text()
    assert "# Rendered brief" in (store.run_dir / "report.md").read_text()
