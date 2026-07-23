# Getting Started

Goal: from a clean machine to a live fleet pipeline in **under five minutes** of active work (image pulls may take longer the first time).

## Prerequisites

- Docker Desktop / Docker Engine with Compose v2
- ~8 GB RAM free for the full stack (32 compose services)
- `curl`, `openssl` (macOS/Linux)

Optional: Go 1.22+, Python 3.12+, Node 22+ for component-local work.

## Minute 0–1 — clone and env

```bash
git clone https://github.com/hamidmatiny/Argus.git
cd Argus
cp .env.example .env
```

Set a real NextAuth secret (required for the dashboard):

```bash
echo "NEXTAUTH_SECRET=$(openssl rand -base64 32)" >> .env
echo "NEXTAUTH_URL=http://localhost:3002" >> .env
echo "AUTH_DEMO_OFFLINE=true" >> .env
echo "LLM_PROVIDER=mock" >> .env
echo "EMBEDDING_PROVIDER=hash" >> .env
```

## Minute 1–4 — bring the platform up

```bash
docker compose up -d --build
```

Wait until critical health checks pass:

```bash
curl -sf http://localhost:8099/health && echo gateway_ok
curl -sf http://localhost:8091/health && echo simulator_ok
curl -sf http://localhost:8093/health && echo qa_ok
```

Or: `make up` (same as compose).

## Minute 4–5 — prove data is flowing

```bash
# Public ping
curl -s http://localhost:8099/v1/ping

# Telemetry via gateway (demo API key)
curl -s -X POST http://localhost:8099/v1/telemetry/query \
  -H 'Content-Type: application/json' \
  -H 'X-API-Key: demo-viewer' \
  -d '{"sql":"SELECT vehicle_id FROM telemetry LIMIT 5","limit":5}'
```

Open in a browser:

| Surface | URL | Notes |
|---------|-----|-------|
| Operator dashboard | http://localhost:3002 | Login `operator` / `operator` if offline demo |
| Grafana | http://localhost:3001 | `admin` / see `GRAFANA_ADMIN_PASSWORD` in `.env` |
| Redpanda Console | http://localhost:8087 | Topics & consumers |
| Dagster | http://localhost:3000 | Asset materializations |
| Prometheus | http://localhost:9090 | Raw metrics |

## What you should see

1. Simulator publishing ~10 Hz across 12 vehicles (`SIMULATOR_*` in `.env`).
2. Stream-processor QA rejecting a small fraction (`SIMULATOR_FAILURE_RATE=0.05`).
3. Lakehouse writers appending to Iceberg; Trino queryable via gateway.
4. Drift-monitor and incident-engine producing incidents over longer windows.

## Next

- Follow the literal [Demo Script](DEMO_SCRIPT.md) for a hiring-manager walkthrough.
- Skim [Architecture](architecture.md) and the [ADRs](adr/index.md).
- Tear down: `docker compose down -v` (volumes optional).
