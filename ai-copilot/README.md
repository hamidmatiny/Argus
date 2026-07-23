# ai-copilot/

LLM-powered **read-only** operations assistant for ARGUS. Combines RAG over
runbooks + historical incidents (Qdrant) with a tool-calling agent that
queries live platform APIs.

> This agent **cannot mutate state**. It will not acknowledge/resolve
> incidents or trigger retraining. Those remain operator actions via the
> dashboard / `argusctl` / gateway.

## What it does

See the narrative sections below for responsibilities and scope.

## Architecture

```text
question → guardrails → LLM (OpenAI-compatible | Anthropic | mock)
                │
                ├─ query_incidents        → incident-engine
                ├─ query_drift_report     → drift-monitor (+ report files)
                ├─ query_telemetry        → api-gateway (SELECT-only SQL)
                ├─ search_runbooks        → Qdrant
                └─ search_similar_incidents → Qdrant
```

Gateway exposure: `POST /v1/copilot/ask` (OPA: viewer+).  
Dashboard: **Ask the fleet** panel → `/api/gateway/v1/copilot/ask`.

## Tool contract

| Tool | Side effects | Notes |
|------|--------------|-------|
| `query_incidents` | none | Optional `status`, `vehicle_id` |
| `query_drift_report` | none | Health + latest Evidently/signal files |
| `query_telemetry` | none | `SELECT` only; tables `telemetry` / `quarantine` |
| `search_runbooks` | none | Vector search |
| `search_similar_incidents` | none | Vector search |

Allow-list enforced in `agent/guardrails.py`. Invented mutation tools are rejected.

## Guardrails

1. **Prompt-injection patterns** rejected before any LLM/tool call  
2. **Tool allow-list** — blocked names include ack/resolve/retrain/shell  
3. **SQL sanitizer** — forbids DDL/DML; requires SELECT on approved tables  
4. **Max tool depth** — `COPILOT_MAX_TOOL_DEPTH` (default 6)

## Config / secrets

All keys from the environment (never hardcoded). Set via
`argusctl secrets set …` when using real providers.

| Var | Purpose |
|-----|---------|
| `LLM_PROVIDER` | `openai` (default HTTP), `anthropic`, or `mock` (CI) |
| `LLM_API_KEY` / `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` | Provider secret |
| `LLM_API_BASE_URL` | OpenAI-compatible base (Groq, xAI, vLLM, …) |
| `LLM_MODEL` | Chat model id |
| `EMBEDDING_PROVIDER` | `hash` (offline) or `openai` |
| `QDRANT_URL` | Vector store |
| `INCIDENT_ENGINE_URL`, `DRIFT_MONITOR_URL`, `ARGUS_GATEWAY_URL` | Tool backends |

Missing LLM key with non-mock provider → `/health` returns
`{"status":"config_error","service":"ai-copilot",…}` (fail-visible).

## Local run

```bash
docker compose up -d --build qdrant ai-copilot
curl -s localhost:8090/health | jq .
curl -s -X POST localhost:8090/copilot/ask \
  -H 'content-type: application/json' \
  -d '{"question":"why did vehicle VH-0003 trip its breaker at 14:02?"}' | jq .
```

Re-index:

```bash
cd ai-copilot && pip install -r requirements.txt
LLM_PROVIDER=mock EMBEDDING_PROVIDER=hash QDRANT_URL=http://localhost:6333 \
  python -m ingestion.index --recreate
```

## Eval harness

Fixed cases in `eval/cases.json` (tool expectations + answer facts).

```bash
cd ai-copilot
LLM_PROVIDER=mock EMBEDDING_PROVIDER=hash QDRANT_URL=http://localhost:6333 \
  python eval/run_eval.py
```

Output JSON: `passed` / `total` / per-case `tools_used`, `missing_facts`.
CI gate: score ≥ 0.7. Unit tests: `pytest tests/ -q`.

### Reading results

- `pass: true` — expected tools (or a sufficient subset) ran; facts appear in
  the answer or tool payloads; no forbidden tools.
- `expect_reject` cases must be blocked by guardrails (injection).
- `sql_injection` asserts the SQL guard rejects `DROP`.