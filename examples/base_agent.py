"""Optional minimal Strands agent, independent of the task-board application.

Usage:
    .venv/bin/python -m examples.base_agent "Explain what agent handoffs are."
    .venv/bin/python -m examples.base_agent --provider mistral "Explain what agent handoffs are."
"""

from __future__ import annotations

import os
import sys

from dotenv import load_dotenv
from mcp import StdioServerParameters, stdio_client
from strands import Agent
from strands.models import GeminiModel
from strands.tools.mcp import MCPClient


DEFAULT_MODEL = "gemini-3-flash-preview"
DEFAULT_MISTRAL_MODEL = "mistral-small-2506"
SYSTEM_PROMPT = "You are a concise, helpful research-assistant prototype."


def build_agent(provider: str = "gemini") -> Agent:
    """Create one provider-selected Strands agent with arXiv paper search."""
    load_dotenv()
    api_key_name = "GEMINI_API_KEY" if provider == "gemini" else "MISTRAL_API_KEY"
    api_key = os.environ.get(api_key_name)
    if not api_key:
        raise RuntimeError(f"{api_key_name} is not set. Add it to .env or your environment.")

    if provider == "gemini":
        model = GeminiModel(
            client_args={"api_key": api_key},
            model_id=os.environ.get("GEMINI_MODEL", DEFAULT_MODEL),
            params={"temperature": 0.2, "max_output_tokens": 512},
        )
    elif provider == "mistral":
        from strands.models.mistral import MistralModel

        model = MistralModel(
            api_key=api_key,
            model_id=os.environ.get("MISTRAL_MODEL", DEFAULT_MISTRAL_MODEL),
            max_tokens=512,
            temperature=0.2,
        )
    else:
        raise ValueError(f"Unsupported provider: {provider}")
    arxiv_client = MCPClient(
        lambda: stdio_client(
            StdioServerParameters(
                command="uvx",
                args=["arxiv-mcp-server"],
            )
        ),
        tool_filters={"allowed": ["search_papers"]},
        prefix="arxiv",
    )

    return Agent(model=model, system_prompt=SYSTEM_PROMPT, callback_handler=None, tools=[arxiv_client])


def main() -> None:
    arguments = sys.argv[1:]
    provider = "gemini"
    if arguments[:1] == ["--provider"]:
        if len(arguments) < 2 or arguments[1] not in {"gemini", "mistral"}:
            raise SystemExit("--provider must be gemini or mistral")
        provider = arguments[1]
        arguments = arguments[2:]
    prompt = " ".join(arguments).strip()
    if not prompt:
        raise SystemExit('Usage: .venv/bin/python -m examples.base_agent [--provider gemini|mistral] "Your prompt"')

    result = build_agent(provider)(prompt)
    print(result)


if __name__ == "__main__":
    main()
