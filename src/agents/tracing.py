"""Safe, host-captured Strands callback tracing for one agent invocation."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, TextIO

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from strands.telemetry import StrandsTelemetry


SENSITIVE_KEYS = frozenset({"api_key", "apikey", "authorization", "password", "secret", "token"})
REASONING_KEYS = frozenset({"reasoningtext", "reasoning_content", "chain_of_thought"})


class AgentTraceCallback:
    """Emit observable Strands callback events to stdout for runner log capture."""

    def __init__(self, run_id: str, task_id: str, profile: str) -> None:
        self.run_id = run_id
        self.task_id = task_id
        self.profile = profile

    def __call__(self, **event: Any) -> None:
        payload = {
            "at": datetime.now(timezone.utc).isoformat(),
            "event": "agent_callback",
            "run_id": self.run_id,
            "task_id": self.task_id,
            "profile": self.profile,
            "payload": self._sanitize(event),
        }
        print(json.dumps(payload, sort_keys=True, default=str), flush=True)

    @classmethod
    def _sanitize(cls, value: Any) -> Any:
        if isinstance(value, dict):
            sanitized: dict[str, Any] = {}
            for key, item in value.items():
                normalized = str(key).lower()
                if normalized in SENSITIVE_KEYS:
                    sanitized[str(key)] = "[REDACTED]"
                elif normalized not in REASONING_KEYS:
                    sanitized[str(key)] = cls._sanitize(item)
            return sanitized
        if isinstance(value, (list, tuple)):
            return [cls._sanitize(item) for item in value]
        if hasattr(value, "model_dump"):
            return cls._sanitize(value.model_dump(mode="json"))
        if isinstance(value, (str, int, float, bool)) or value is None:
            return value
        return str(value)


_TRACE_STREAMS: list[TextIO] = []


def configure_local_otel_trace(path: Path) -> None:
    """Configure Strands' documented standard OTel exporters in a fresh worker."""
    provider = TracerProvider()
    trace.set_tracer_provider(provider)
    stream = path.open("w", encoding="utf-8")
    _TRACE_STREAMS.append(stream)
    telemetry = StrandsTelemetry(tracer_provider=provider).setup_console_exporter(out=stream)
    if os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT"):
        telemetry.setup_otlp_exporter()
