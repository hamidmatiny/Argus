# ai-copilot

LLM-backed **query and explain** layer that sits alongside the data plane. Answers natural-language questions about fleet health, incidents, and data quality using governed access to lakehouse and incident APIs.

**Status:** Scaffold only — implemented in a later phase.

**Language:** Python

**Responsibilities (planned):**
- RAG / tool-calling over Iceberg metadata and incident APIs
- Guardrails and OPA-aware data access
- Streaming responses for dashboard and CLI
