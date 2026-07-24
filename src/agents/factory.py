"""Fresh, least-privilege Strands worker construction."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from mcp import StdioServerParameters, stdio_client
from strands import Agent
from strands.models import GeminiModel
from strands.sandbox import Sandbox
from strands.tools.mcp import MCPClient
from strands.vended_plugins.skills import AgentSkills, Skill

from src.agents.profiles import WorkerProfile
from src.agents.tracing import AgentTraceCallback, configure_local_otel_trace
from src.agents.tools import allowed_artifact_reader, source_discovery_tools
from src.state.models import TaskRecord
from src.state.run_store import RunStore


DEFAULT_MODEL = "gemini-3.5-flash-lite"
DEFAULT_MISTRAL_MODEL = "mistral-small-2506"


def build_worker_agent(
    *,
    store: RunStore,
    task: TaskRecord,
    profile: WorkerProfile,
    sandbox: Sandbox,
    run_id: str,
    model_provider: str = "gemini",
) -> Agent:
    """Create a fresh agent with only task-approved capabilities.

    Skill files are loaded eagerly into ``Skill`` objects so their instruction
    text is available even when the Docker sandbox exposes a different path.
    """
    load_dotenv()
    api_key_name = "GEMINI_API_KEY" if model_provider == "gemini" else "MISTRAL_API_KEY"
    api_key = os.environ.get(api_key_name)
    if not api_key:
        raise RuntimeError(f"{api_key_name} is required for {model_provider} worker mode.")
    configure_local_otel_trace(store.otel_trace_path(task.id, task.attempt))

    if model_provider == "gemini":
        model = GeminiModel(
            client_args={"api_key": api_key},
            model_id=os.environ.get("GEMINI_MODEL", DEFAULT_MODEL),
            params={"max_output_tokens": profile.max_tokens},
        )
    elif model_provider == "mistral":
        from strands.models.mistral import MistralModel

        model = MistralModel(
            api_key=api_key,
            model_id=os.environ.get("MISTRAL_MODEL", DEFAULT_MISTRAL_MODEL),
            max_tokens=profile.max_tokens,
        )
    else:
        raise ValueError(f"Unsupported model provider: {model_provider}")
    tools = [allowed_artifact_reader(store, task)]
    if profile.enable_ddg_search:
        tools.extend(source_discovery_tools(sandbox))
    if profile.enable_arxiv:
        tools.append(
            MCPClient(
                lambda: stdio_client(
                    StdioServerParameters(command="uvx", args=["arxiv-mcp-server"])
                ),
                tool_filters={"allowed": ["search_papers"]},
                prefix="arxiv",
            )
        )
    skills = [Skill.from_file(Path(path), strict=True) for path in profile.skill_paths]
    prompt = (
        f"You are the {profile.name} worker. Work only on the assigned task. "
        "Use only artifacts named in the task envelope. Do not claim unsupported facts."
    )
    return Agent(
        model=model,
        system_prompt=prompt,
        tools=tools,
        plugins=[AgentSkills(skills=skills, strict=True)],
        callback_handler=AgentTraceCallback(run_id=run_id, task_id=task.id, profile=profile.name),
        sandbox=sandbox,
        trace_attributes={"run.id": run_id, "task.id": task.id, "profile": profile.name},
    )
