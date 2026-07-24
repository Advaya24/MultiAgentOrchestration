"""Safety properties of persisted observable agent traces."""

from __future__ import annotations

from pathlib import Path

from src.agents import tracing
from src.agents.tracing import AgentTraceCallback


def test_agent_trace_redacts_credentials_and_reasoning(capsys) -> None:
    callback = AgentTraceCallback(run_id="run-1", task_id="T-001", profile="writer")

    callback(api_key="secret", reasoningText="hidden", event={"data": "visible"})

    output = capsys.readouterr().out
    assert "[REDACTED]" in output
    assert "hidden" not in output
    assert "visible" in output


def test_otel_configuration_enables_otlp_when_endpoint_is_set(monkeypatch, tmp_path) -> None:
    configured: list[object] = []

    class FakeTelemetry:
        def __init__(self, *, tracer_provider: object) -> None:
            configured.append(tracer_provider)

        def setup_console_exporter(self, **_kwargs: object) -> "FakeTelemetry":
            configured.append("console")
            return self

        def setup_otlp_exporter(self) -> "FakeTelemetry":
            configured.append("otlp")
            return self

    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4318")
    monkeypatch.setattr(tracing, "StrandsTelemetry", FakeTelemetry)
    monkeypatch.setattr(tracing.trace, "set_tracer_provider", lambda _provider: None)

    tracing.configure_local_otel_trace(Path(tmp_path / "trace.jsonl"))

    assert configured[1:] == ["console", "otlp"]
