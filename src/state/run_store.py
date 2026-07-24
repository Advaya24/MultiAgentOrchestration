"""Markdown-backed durable run state with atomic scheduler writes."""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from datetime import datetime, timezone
from html import escape
from pathlib import Path
from statistics import median
from typing import Any

import yaml
import matplotlib

matplotlib.use("Agg")
from matplotlib import pyplot as plt

from .models import ArtifactDraft, CompletionProposal, TaskRecord


class RunStore:
    """Own the inspectable files for one run.

    Only the scheduler should call task and artifact write methods. Workers may
    write completion proposals to ``inbox/`` through ``write_proposal``.
    """

    def __init__(self, run_dir: Path) -> None:
        self.run_dir = run_dir
        self.tasks_dir = run_dir / "tasks"
        self.artifacts_dir = run_dir / "artifacts"
        self.inbox_dir = run_dir / "inbox"
        self.logs_dir = run_dir / "logs"
        self.traces_dir = run_dir / "traces"
        for directory in (self.tasks_dir, self.artifacts_dir, self.inbox_dir, self.logs_dir, self.traces_dir):
            directory.mkdir(parents=True, exist_ok=True)

    def create_task(self, task: TaskRecord) -> None:
        path = self._task_path(task.id)
        if path.exists():
            raise ValueError(f"Task already exists: {task.id}")
        self._write_markdown(path, task.model_dump(mode="json", exclude={"instruction", "acceptance_criteria"}), self._task_body(task))

    def read_task(self, task_id: str) -> TaskRecord:
        metadata, body = self._read_markdown(self._task_path(task_id))
        instruction, criteria = self._parse_task_body(body)
        return TaskRecord.model_validate({**metadata, "instruction": instruction, "acceptance_criteria": criteria})

    def update_task(self, task: TaskRecord) -> None:
        self._write_markdown(
            self._task_path(task.id),
            task.model_dump(mode="json", exclude={"instruction", "acceptance_criteria"}),
            self._task_body(task),
        )

    def list_tasks(self) -> list[TaskRecord]:
        return [self.read_task(path.stem) for path in sorted(self.tasks_dir.glob("T-*.md"))]

    def write_artifact(self, task_id: str, draft: ArtifactDraft) -> str:
        artifact_id = f"A-{len(list(self.artifacts_dir.glob('A-*.md'))) + 1:03d}"
        metadata = {
            "id": artifact_id,
            "task_id": task_id,
            "kind": draft.kind,
            "input_artifacts": draft.input_artifacts,
            "payload": draft.payload,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        self._write_markdown(self.artifacts_dir / f"{artifact_id}.md", metadata, draft.summary)
        return artifact_id

    def read_artifact(self, artifact_id: str) -> dict[str, Any]:
        metadata, body = self._read_markdown(self.artifacts_dir / f"{artifact_id}.md")
        return {**metadata, "summary": body.strip()}

    def write_proposal(self, proposal: CompletionProposal, worker_id: str) -> Path:
        """Write an untrusted worker result atomically to the scheduler inbox."""
        filename = f"completion-{proposal.task_id}-{proposal.attempt}-{worker_id}.json"
        path = self.inbox_dir / filename
        self._atomic_write(path, json.dumps(proposal.model_dump(mode="json"), indent=2) + "\n")
        return path

    def worker_log_path(self, task_id: str, attempt: int) -> Path:
        """Return the host-captured stdout/stderr path for one worker attempt."""
        return self.logs_dir / f"{task_id.lower()}-attempt-{attempt}.log"

    def otel_trace_path(self, task_id: str, attempt: int) -> Path:
        """Return the native Strands OpenTelemetry span export path for an attempt."""
        return self.traces_dir / f"{task_id.lower()}-attempt-{attempt}.otel.json"

    def consume_proposals(self) -> list[CompletionProposal]:
        proposals: list[CompletionProposal] = []
        for path in sorted(self.inbox_dir.glob("completion-*.json")):
            processing = path.with_suffix(".processing")
            os.replace(path, processing)
            try:
                proposals.append(CompletionProposal.model_validate_json(processing.read_text()))
            finally:
                processing.unlink(missing_ok=True)
        return proposals

    def append_event(self, event: str, **fields: object) -> None:
        payload = {"at": datetime.now(timezone.utc).isoformat(), "event": event, **fields}
        with (self.run_dir / "events.md").open("a", encoding="utf-8") as stream:
            stream.write(f"- `{payload['at']}` **{event}** `{json.dumps(fields, sort_keys=True)}`\n")
        with (self.run_dir / "trace.jsonl").open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(payload, sort_keys=True) + "\n")
        self.render_board()

    def render_board(self) -> None:
        rows = ["# Task board", "", "| ID | Type | Status | Attempt |", "| --- | --- | --- | ---: |"]
        tasks = self.list_tasks()
        for task in tasks:
            rows.append(f"| {task.id} | {task.type} | {task.status.value} | {task.attempt} |")
        self._atomic_write(self.run_dir / "board.md", "\n".join(rows) + "\n")
        self.render_task_graph(tasks)
        self.render_dashboard()

    def render_dashboard(self) -> None:
        """Derive inspectable request metrics and the latest human-facing brief."""
        requests = self._model_requests()
        total_input = sum(item["input_tokens"] for item in requests)
        total_output = sum(item["output_tokens"] for item in requests)
        latencies = [item["latency_ms"] for item in requests if item["latency_ms"] is not None]
        first_tokens = [item["time_to_first_token_ms"] for item in requests if item["time_to_first_token_ms"] is not None]
        metrics = {
            "request_count": len(requests),
            "input_tokens": total_input,
            "output_tokens": total_output,
            "total_tokens": total_input + total_output,
            "latency_ms": self._metric_summary(latencies),
            "time_to_first_token_ms": self._metric_summary(first_tokens),
            "requests": requests,
        }
        self._atomic_write(self.run_dir / "metrics.json", json.dumps(metrics, indent=2) + "\n")
        self._render_stats_chart(metrics, self.run_dir / "stats.png")
        self._atomic_write(self.run_dir / "stats.md", self._stats_markdown(metrics))
        self._atomic_write(self.run_dir / "report.md", self._latest_brief_markdown())

    def render_task_graph(self, tasks: list[TaskRecord] | None = None) -> None:
        """Derive D2, SVG, and Mermaid task graphs from authoritative task files."""
        tasks = tasks if tasks is not None else self.list_tasks()
        d2_path = self.run_dir / "task_graph.d2"
        self._atomic_write(d2_path, self._d2_task_graph(tasks))
        self._render_d2_svg(d2_path, self.run_dir / "task_graph.svg")
        self._atomic_write(self.run_dir / "task_graph.md", self._mermaid_task_graph(tasks))

    def next_task_id(self) -> str:
        return f"T-{len(list(self.tasks_dir.glob('T-*.md'))) + 1:03d}"

    def _task_path(self, task_id: str) -> Path:
        return self.tasks_dir / f"{task_id}.md"

    @staticmethod
    def _task_body(task: TaskRecord) -> str:
        criteria = "\n".join(f"- {item}" for item in task.acceptance_criteria) or "- Complete the task contract."
        return f"## Instruction\n\n{task.instruction}\n\n## Acceptance criteria\n\n{criteria}\n"

    @staticmethod
    def _parse_task_body(body: str) -> tuple[str, list[str]]:
        instruction_marker = "## Instruction\n\n"
        criteria_marker = "\n\n## Acceptance criteria\n\n"
        if instruction_marker not in body or criteria_marker not in body:
            raise ValueError("Task body does not match task-board contract")
        instruction = body.split(instruction_marker, 1)[1].split(criteria_marker, 1)[0].strip()
        criteria_section = body.split(criteria_marker, 1)[1]
        criteria = [line[2:] for line in criteria_section.splitlines() if line.startswith("- ")]
        return instruction, criteria

    def _write_markdown(self, path: Path, metadata: dict[str, Any], body: str) -> None:
        content = f"---\n{yaml.safe_dump(metadata, sort_keys=False).strip()}\n---\n\n{body.strip()}\n"
        self._atomic_write(path, content)

    @staticmethod
    def _read_markdown(path: Path) -> tuple[dict[str, Any], str]:
        content = path.read_text(encoding="utf-8")
        if not content.startswith("---\n"):
            raise ValueError(f"Missing YAML front matter: {path}")
        _, raw_metadata, body = content.split("---\n", 2)
        metadata = yaml.safe_load(raw_metadata)
        if not isinstance(metadata, dict):
            raise ValueError(f"Invalid front matter: {path}")
        return metadata, body

    @staticmethod
    def _atomic_write(path: Path, content: str) -> None:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as stream:
            stream.write(content)
            temporary_path = Path(stream.name)
        os.replace(temporary_path, path)

    @staticmethod
    def _d2_task_graph(tasks: list[TaskRecord]) -> str:
        colors = {
            "pending": "#d1d5db",
            "ready": "#bfdbfe",
            "claimed": "#fde68a",
            "awaiting_review": "#ddd6fe",
            "complete": "#bbf7d0",
            "blocked": "#fecaca",
            "failed": "#fecaca",
            "stale": "#fed7aa",
            "cancelled": "#e5e7eb",
        }
        lines = ["direction: down", "", "# Generated from tasks/*.md; do not edit as workflow state."]
        for task in tasks:
            key = RunStore._graph_key(task.id)
            label = json.dumps(f"{task.id}\n{task.type}\n{task.status.value} · attempt {task.attempt}")
            lines.extend(
                [
                    f"{key}: {{",
                    f"  label: {label}",
                    "  shape: rectangle",
                    f'  style.fill: "{colors[task.status.value]}"',
                    "}",
                ]
            )
        for task in tasks:
            for dependency in task.depends_on:
                lines.append(f"{RunStore._graph_key(dependency)} -> {RunStore._graph_key(task.id)}")
        return "\n".join(lines) + "\n"

    @staticmethod
    def _mermaid_task_graph(tasks: list[TaskRecord]) -> str:
        lines = ["# Live task graph", "", "```mermaid", "flowchart TD"]
        for task in tasks:
            label = (
                f"{escape(task.id)}<br/>{escape(task.type)}<br/>"
                f"{escape(task.status.value)} · attempt {task.attempt}"
            )
            lines.append(f'  {RunStore._graph_key(task.id)}["{label}"]')
        for task in tasks:
            for dependency in task.depends_on:
                lines.append(f"  {RunStore._graph_key(dependency)} --> {RunStore._graph_key(task.id)}")
        for status, color in {
            "pending": "#d1d5db",
            "ready": "#bfdbfe",
            "claimed": "#fde68a",
            "awaiting_review": "#ddd6fe",
            "complete": "#bbf7d0",
            "blocked": "#fecaca",
            "failed": "#fecaca",
            "stale": "#fed7aa",
            "cancelled": "#e5e7eb",
        }.items():
            lines.append(f"  classDef {status} fill:{color},stroke:#475569")
        for task in tasks:
            lines.append(f"  class {RunStore._graph_key(task.id)} {task.status.value}")
        lines.extend(["```", "", "Generated from `tasks/*.md`; do not edit as workflow state."])
        return "\n".join(lines) + "\n"

    @staticmethod
    def _graph_key(task_id: str) -> str:
        return "task_" + "".join(character if character.isalnum() else "_" for character in task_id)

    @staticmethod
    def _render_d2_svg(source: Path, target: Path) -> None:
        """Render graph output atomically so viewers never receive a partial SVG."""
        with tempfile.NamedTemporaryFile(suffix=".svg", dir=target.parent, delete=False) as stream:
            temporary_target = Path(stream.name)
        try:
            result = subprocess.run(
                ["d2", str(source), str(temporary_target)],
                check=False,
                capture_output=True,
                text=True,
            )
            if result.returncode:
                raise RuntimeError(f"D2 graph rendering failed: {result.stderr.strip()}")
            os.replace(temporary_target, target)
        finally:
            temporary_target.unlink(missing_ok=True)

    def _model_requests(self) -> list[dict[str, Any]]:
        requests: list[dict[str, Any]] = []
        for path in sorted(self.traces_dir.glob("*.otel.json")):
            for span in self._read_json_stream(path):
                # Strands emits an aggregate ``invoke_agent`` span whose token
                # attributes sum its child chat spans. Count only provider chat
                # invocations so run totals do not double-count that aggregate.
                if span.get("name") != "chat":
                    continue
                attributes = span.get("attributes", {})
                if not isinstance(attributes, dict) or "gen_ai.usage.total_tokens" not in attributes:
                    continue
                start = self._parse_otel_timestamp(span.get("start_time"))
                end = self._parse_otel_timestamp(span.get("end_time"))
                requests.append(
                    {
                        "trace_file": path.relative_to(self.run_dir).as_posix(),
                        "task_id": attributes.get("task.id", "unknown"),
                        "profile": attributes.get("profile", "unknown"),
                        "model": attributes.get("gen_ai.request.model", "unknown"),
                        "input_tokens": int(attributes.get("gen_ai.usage.input_tokens", attributes.get("gen_ai.usage.prompt_tokens", 0))),
                        "output_tokens": int(attributes.get("gen_ai.usage.output_tokens", attributes.get("gen_ai.usage.completion_tokens", 0))),
                        "total_tokens": int(attributes["gen_ai.usage.total_tokens"]),
                        "latency_ms": round((end - start).total_seconds() * 1000, 2) if start and end else None,
                        "time_to_first_token_ms": attributes.get("gen_ai.server.time_to_first_token"),
                    }
                )
        return requests

    @staticmethod
    def _read_json_stream(path: Path) -> list[dict[str, Any]]:
        """Read ConsoleSpanExporter JSON objects, tolerating an in-progress trace file."""
        decoder = json.JSONDecoder()
        content = path.read_text(encoding="utf-8")
        position = 0
        objects: list[dict[str, Any]] = []
        while position < len(content):
            while position < len(content) and content[position].isspace():
                position += 1
            if position >= len(content):
                break
            try:
                value, position = decoder.raw_decode(content, position)
            except json.JSONDecodeError:
                break
            if isinstance(value, dict):
                objects.append(value)
        return objects

    @staticmethod
    def _parse_otel_timestamp(value: object) -> datetime | None:
        if not isinstance(value, str):
            return None
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None

    @staticmethod
    def _metric_summary(values: list[float | int]) -> dict[str, float | int | None]:
        if not values:
            return {"sum": 0, "average": None, "p50": None, "p95": None}
        ordered = sorted(values)
        p95_index = max(0, min(len(ordered) - 1, int(len(ordered) * 0.95 + 0.999999) - 1))
        return {
            "sum": round(sum(values), 2),
            "average": round(sum(values) / len(values), 2),
            "p50": round(median(values), 2),
            "p95": round(ordered[p95_index], 2),
        }

    @staticmethod
    def _stats_markdown(metrics: dict[str, Any]) -> str:
        lines = [
            "# Run statistics",
            "",
            "Generated from local OpenTelemetry model-invocation spans.",
            "",
            "![Token and latency by model request](stats.png)",
            "",
            "| Metric | Value |",
            "| --- | ---: |",
            f"| Model requests | {metrics['request_count']} |",
            f"| Input tokens | {metrics['input_tokens']} |",
            f"| Output tokens | {metrics['output_tokens']} |",
            f"| Total tokens | {metrics['total_tokens']} |",
            f"| Latency average (ms) | {metrics['latency_ms']['average'] or '—'} |",
            f"| Latency p50 / p95 (ms) | {metrics['latency_ms']['p50'] or '—'} / {metrics['latency_ms']['p95'] or '—'} |",
            f"| Time to first token average (ms) | {metrics['time_to_first_token_ms']['average'] or '—'} |",
            "",
            "## Requests",
            "",
            "| Task | Profile | Model | Input | Output | Total | Latency (ms) | Trace |",
            "| --- | --- | --- | ---: | ---: | ---: | ---: | --- |",
        ]
        for item in metrics["requests"]:
            lines.append(
                f"| {item['task_id']} | {item['profile']} | {item['model']} | {item['input_tokens']} | "
                f"{item['output_tokens']} | {item['total_tokens']} | {item['latency_ms'] or '—'} | "
                f"[{item['trace_file']}]({item['trace_file']}) |"
            )
        return "\n".join(lines) + "\n"

    @staticmethod
    def _render_stats_chart(metrics: dict[str, Any], target: Path) -> None:
        """Render task summaries plus color-grouped request-level metrics."""
        requests = metrics["requests"]
        task_order: list[str] = []
        task_totals: dict[str, dict[str, float]] = {}
        for item in requests:
            task_id = str(item["task_id"])
            if task_id not in task_totals:
                task_order.append(task_id)
                task_totals[task_id] = {"input": 0, "output": 0, "latency": 0}
            task_totals[task_id]["input"] += item["input_tokens"]
            task_totals[task_id]["output"] += item["output_tokens"]
            task_totals[task_id]["latency"] += item["latency_ms"] or 0
        if not task_order:
            task_order = ["No requests yet"]
            task_totals = {"No requests yet": {"input": 0, "output": 0, "latency": 0}}

        palette = ["#4f46e5", "#059669", "#d97706", "#db2777", "#0284c7", "#7c3aed", "#65a30d", "#dc2626"]
        task_colors = {task_id: palette[index % len(palette)] for index, task_id in enumerate(task_order)}
        call_labels: list[str] = []
        call_tokens: list[int] = []
        call_latency: list[float] = []
        call_colors: list[str] = []
        call_groups: list[tuple[str, int, int]] = []
        start = 0
        current_task: str | None = None
        task_call_number = 0
        for index, item in enumerate(requests):
            task_id = str(item["task_id"])
            if task_id != current_task:
                if current_task is not None:
                    call_groups.append((current_task, start, index - 1))
                current_task = task_id
                start = index
                task_call_number = 0
            task_call_number += 1
            call_labels.append(f"{task_id}\n#{task_call_number}")
            call_tokens.append(item["total_tokens"])
            call_latency.append(item["latency_ms"] or 0)
            call_colors.append(task_colors[task_id])
        if current_task is not None:
            call_groups.append((current_task, start, len(requests) - 1))
        if not call_labels:
            call_labels, call_tokens, call_latency, call_colors = ["—"], [0], [0], ["#94a3b8"]

        figure, axes = plt.subplots(2, 2, figsize=(15, max(7, len(call_labels) * 0.42 + 4)))
        figure.patch.set_facecolor("#f8fafc")
        task_positions = list(range(len(task_order)))
        token_axis, task_latency_axis, call_token_axis, call_latency_axis = axes.ravel()
        task_input = [task_totals[task_id]["input"] for task_id in task_order]
        task_output = [task_totals[task_id]["output"] for task_id in task_order]
        task_latency = [task_totals[task_id]["latency"] for task_id in task_order]
        token_axis.barh(task_positions, task_input, color="#4f46e5", label="Input")
        token_axis.barh(task_positions, task_output, left=task_input, color="#a5b4fc", label="Output")
        token_axis.set_title("Tokens by task", loc="left", fontweight="bold")
        token_axis.set_xlabel("Tokens")
        token_axis.set_yticks(task_positions, task_order)
        token_axis.legend(frameon=False, ncols=2)
        task_latency_axis.barh(task_positions, task_latency, color=[task_colors[task_id] for task_id in task_order])
        task_latency_axis.set_title("Total invocation latency by task", loc="left", fontweight="bold")
        task_latency_axis.set_xlabel("Milliseconds")
        task_latency_axis.set_yticks(task_positions, task_order)

        call_positions = list(range(len(call_labels)))
        call_token_axis.bar(call_positions, call_tokens, color=call_colors)
        call_token_axis.set_title("Tokens by model call", loc="left", fontweight="bold")
        call_token_axis.set_ylabel("Tokens")
        call_latency_axis.bar(call_positions, call_latency, color=call_colors)
        call_latency_axis.set_title("Latency by model call", loc="left", fontweight="bold")
        call_latency_axis.set_ylabel("Milliseconds")
        for axis in (call_token_axis, call_latency_axis):
            axis.set_xticks(call_positions, call_labels, fontsize=8)
            for task_id, group_start, group_end in call_groups:
                axis.axvspan(group_start - 0.5, group_end + 0.5, color=task_colors[task_id], alpha=0.08)
                axis.axvline(group_end + 0.5, color="#cbd5e1", linewidth=0.7)
        for axis in axes.ravel():
            axis.set_facecolor("#ffffff")
            axis.grid(axis="x", color="#e2e8f0")
            axis.set_axisbelow(True)
        token_axis.invert_yaxis()
        task_latency_axis.invert_yaxis()
        figure.suptitle(
            f"Run dashboard — {metrics['request_count']} requests, {metrics['total_tokens']:,} total tokens",
            x=0.08,
            ha="left",
            fontweight="bold",
        )
        figure.tight_layout(rect=(0, 0, 1, 0.94))
        with tempfile.NamedTemporaryFile(suffix=".png", dir=target.parent, delete=False) as stream:
            temporary_target = Path(stream.name)
        try:
            figure.savefig(temporary_target, dpi=160, bbox_inches="tight")
            os.replace(temporary_target, target)
        finally:
            plt.close(figure)
            temporary_target.unlink(missing_ok=True)

    def _latest_brief_markdown(self) -> str:
        briefs = [
            artifact
            for path in sorted(self.artifacts_dir.glob("A-*.md"))
            if (artifact := self.read_artifact(path.stem)).get("kind") in {"brief", "research_brief"}
        ]
        if not briefs:
            return "# Final report\n\n_No research brief has been produced yet._\n"
        latest = briefs[-1]
        payload = latest.get("payload", {})
        content = payload.get("brief_text") or payload.get("content") if isinstance(payload, dict) else None
        if not isinstance(content, str):
            content = latest["summary"]
        return f"<!-- Derived from {latest['id']} ({latest['kind']}); do not edit. -->\n\n{content.rstrip()}\n"
