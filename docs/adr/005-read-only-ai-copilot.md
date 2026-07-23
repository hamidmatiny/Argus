# ADR 005 — Read-only AI copilot

**Status:** Accepted  
**Date:** 2026-07  
**Phase:** 13

## Context

Operators want natural-language investigation (“why did VH-12 trip?”). Giving an LLM `ack` / `resolve` / `retrain` tools is dangerous: hallucinations + automation = silent fleet changes.

## Decision

Ship an **ai-copilot** that:

- Retrieves runbooks from Qdrant (RAG)
- Calls **read-only** tools (query incidents, drift reports, scoped telemetry SQL via gateway)
- **Refuses** mutating actions (acknowledge, resolve, retrain) — humans use dashboard/CLI
- Supports mock LLM for CI/eval without paid keys

## Alternatives considered

| Option | Why not |
|--------|---------|
| Full tool-calling agent with write tools | Unacceptable blast radius for a portfolio default |
| Chat-only with no tools | Hallucinates metrics; cannot cite live state |
| Embed LLM inside incident-engine | Couples hot path to model latency/cost |

## Consequences

- Eval harness (15 scenarios) gates quality with mock provider.
- Guardrails are product features, not afterthoughts — good interview talking point.
- Production still needs human-in-the-loop for any mutation.
