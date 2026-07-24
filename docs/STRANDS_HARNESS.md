# Strands Agents Harness SDK

## What it is

[Strands Agents](https://github.com/strands-agents/harness-sdk) is an open-source agent-harness SDK for Python and TypeScript. It supplies the model-driven agent loop and primitives for models, tools, stateful conversations, multi-agent coordination, hooks, and telemetry. The SDK does not decide this exercise's architecture or research answer; it is one candidate runtime for implementing and observing it.

## Core concepts

- **Agent:** a model plus prompts/messages, tools, and lifecycle hooks. The agent loop lets the model select tools, receives tool results, and continues until it responds.
- **Tools:** callable capabilities supplied to an agent. Python functions can be declared as tools; MCP tools are also supported.
- **Models:** the SDK supports several providers. The documented Python default is Amazon Bedrock, but other providers, including OpenAI, are available.
- **Conversation and context:** the SDK offers null, sliding-window, and summarizing conversation managers. Context management controls in-memory agent history; it does not by itself define durable project artifacts or provenance.
- **Multi-agent patterns:** agents-as-tools, Workflow, Graph, Swarm, and A2A. A Graph provides deterministic dependency-driven execution; a Swarm provides shared context and autonomous handoffs.
- **Hooks and observability:** hooks can inspect or redirect lifecycle steps. Agent results expose metrics and traces; the SDK also supports telemetry integration.

## Minimal Python setup

The official Python quickstart requires Python 3.10+.

```sh
python -m venv .venv
source .venv/bin/activate
python -m pip install strands-agents
```

The optional `strands-agents-tools` package provides community-maintained tools. A configured model provider is also required. The default documented Python configuration uses Amazon Bedrock and AWS credentials; provider-specific configuration differs.

```python
from strands import Agent, tool


@tool
def lookup_source(query: str) -> str:
    """Return permitted source material for a query."""
    # Application-defined implementation.
    raise NotImplementedError


agent = Agent(tools=[lookup_source])
result = agent("Investigate the assigned question using sources.")
```

This is an SDK baseline, not a design recommendation for the assignment.

## Relevance to the research-brief exercise

The use case has both parallel and sequential dependencies: source discovery and extraction may proceed independently, while cross-checking and brief-writing consume selected upstream artifacts. Strands' documented patterns make it possible to experiment with these execution shapes:

- **Graph:** useful to express explicit dependency edges and joins.
- **Agents as tools or Workflow:** useful to model bounded delegation and a staged handoff.
- **Swarm:** useful only if the solution deliberately wants shared context and autonomous agent-to-agent handoffs; that tradeoff may conflict with an exercise focused on scoped context.

The SDK's conversation managers, hooks, traces, and metrics are relevant evidence surfaces for demonstrating context choices and runtime behavior. The exercise still needs its own decisions about research-question scope, artifact schemas, source provenance, persistence, retries, and revision handling.

## Limitations and uncertainties

- Strands is a rapidly evolving SDK. Confirm API signatures, provider defaults, and feature maturity against the official docs at implementation time.
- A framework's multi-agent primitives do not automatically deliver durable work queues, idempotency, cross-run provenance, or targeted invalidation. Those may need application-level design.
- Shared-context patterns can simplify collaboration but may worsen context growth and irrelevant-information exposure.
- Model credentials, provider access, quota, tool permissions, and network availability are deployment concerns outside the SDK's basic abstractions.
- This document does not select a model provider, orchestration pattern, or implementation approach.

## Primary sources

- [Harness SDK repository and current quick starts](https://github.com/strands-agents/harness-sdk)
- [Python quickstart](https://strandsagents.com/docs/user-guide/quickstart/python/)
- [Multi-agent patterns](https://strandsagents.com/docs/user-guide/concepts/multi-agent/)
- [Graph pattern](https://strandsagents.com/docs/user-guide/concepts/multi-agent/graph/)
- [Conversation management](https://strandsagents.com/docs/user-guide/concepts/agents/conversation-management/)
- [Plugins and context facilities](https://strandsagents.com/docs/user-guide/concepts/plugins/)
- [Observability](https://strandsagents.com/docs/user-guide/observability-evaluation/observability/)
