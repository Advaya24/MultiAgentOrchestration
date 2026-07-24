# Gemini Integration Reference

`scripts/gemini_example.py` demonstrates a possible model integration for the solution phase.

## Available Capabilities

- Python client: `google-genai`
- Credential: `GEMINI_API_KEY`
- Model in the example: `models/gemini-3-flash-preview`
- Built-in tool: `google_search`
- Generation controls: temperature, output-token limit, top-p, and thinking level

## Example Shape

```python
from google import genai

client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
interaction = client.interactions.create(
    model="models/gemini-3-flash-preview",
    input="<research request>",
    tools=[{"type": "google_search"}],
    generation_config={...},
)
```

The example prints the final interaction step. It is a starting point, not a committed solution design.

## Before Implementation

- Confirm the supported Gemini model and SDK API at implementation time; the example uses a preview model.
- Decide how retrieved sources, citations, and tool output will be retained for reproducible runs.
- Keep `GEMINI_API_KEY` local; do not commit it.
