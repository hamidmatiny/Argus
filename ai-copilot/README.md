# ai-copilot

LLM-backed **query and explain** layer that sits alongside the data plane. Answers natural-language questions about fleet health, incidents, and data quality using governed access to lakehouse and incident APIs.

**Status:** Scaffold only — implemented in a later phase.

**Language:** Python

**Responsibilities (planned):**
- RAG / tool-calling over Iceberg metadata and incident APIs
- Guardrails and OPA-aware data access
- Streaming responses for dashboard and CLI

## Provider credentials (required)

ai-copilot **must** obtain provider keys from the environment only (repo-root
`.env` via compose). Manage them with:

```bash
argusctl secrets set XAI_API_KEY="..."
argusctl secrets doctor
```

### Fail-fast startup convention

If `XAI_API_KEY` / `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` / `LLM_API_KEY` is
missing or rejected by the provider, the process must **not** start serving
traffic. `/health` (or `/readyz`) returns structured JSON:

```json
{
  "status": "config_error",
  "reason": "XAI_API_KEY rejected by provider (401)",
  "service": "ai-copilot"
}
```

Never crash with an opaque stack trace or silently degrade to a stub model.
See [`cli/README.md`](../cli/README.md) for the platform-wide convention.
