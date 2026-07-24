# Gemini Integration Reference

Gemini is used through Strands' `GeminiModel`, not a separate direct-SDK
prototype. Both workers and the team planner default to `gemini-3.5-flash-lite`;
set `GEMINI_MODEL` locally to override it. Authentication is read only from
`GEMINI_API_KEY` in the environment or ignored `.env` file.

Workers receive only their profile's explicit tools. Web-discovery workers use
the sandboxed `ddg_web_search` and `web_fetch` tools; no generic search or
filesystem tool is exposed. The team planner has no model-callable tools.

Run the live board with:

```sh
.venv/bin/python -m src.cli run --request-file request.md --mode gemini
```

The durable task and artifact contracts, plus local OTel tracing, are described
in [Strands Implementation Contract](STRANDS_IMPLEMENTATION.md).
