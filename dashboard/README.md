# ARGUS Operator Dashboard

Next.js (App Router) UI for fleet health, incidents, data quality, telemetry
exploration, and pipeline status. Talks **only** to `api-gateway` (and
Prometheus / Dagster / MLflow via server-side BFF routes).

## Screenshots

| Page | Placeholder |
|------|-------------|
| Overview | `docs/screenshots/overview.png` (TODO) |
| Incidents | `docs/screenshots/incidents.png` (TODO) |
| Data Quality | `docs/screenshots/data-quality.png` (TODO) |
| Telemetry | `docs/screenshots/telemetry.png` (TODO) |
| Pipeline | `docs/screenshots/pipeline.png` (TODO) |

## Setup

```bash
cd dashboard
cp .env.example .env.local   # optional overrides
npm install
npm run dev                  # http://localhost:3002
```

### Auth

1. **Demo / password grant** — login form posts to Keycloak `argus-gateway`
   public client (`operator` / `operator`, etc.).
2. **OIDC** — “Continue with Keycloak OIDC” uses confidential client
   `argus-dashboard` (secret in compose / `.env`).
3. **Offline e2e** — set `AUTH_DEMO_OFFLINE=true` so Credentials provider
   works without Keycloak (maps viewer/operator/admin usernames to API keys).

Roles drive UI: operators/admins see Acknowledge / Resolve; viewers do not.

### Environment

| Var | Default | Purpose |
|-----|---------|---------|
| `NEXTAUTH_URL` | `http://localhost:3002` | Auth callbacks |
| `NEXTAUTH_SECRET` | *(required)* | Session encryption — `openssl rand -base64 32` |
| `KEYCLOAK_ISSUER` | `http://localhost:8085/realms/argus` | OIDC issuer |
| `KEYCLOAK_CLIENT_ID` | `argus-dashboard` | OIDC client |
| `KEYCLOAK_CLIENT_SECRET` | `argus-dashboard-secret` | OIDC secret |
| `ARGUS_GATEWAY_URL` | `http://localhost:8099` | Server → gateway |
| `PROMETHEUS_URL` | `http://localhost:9090` | Overview gauges |
| `DAGSTER_GRAPHQL_URL` | `http://localhost:3000/graphql` | Pipeline |
| `MLFLOW_TRACKING_URI` | `http://localhost:5002` | Pipeline |
| `AUTH_DEMO_OFFLINE` | `false` | Offline demo login |

Copy `dashboard/.env.example` → `.env.local` for `npm run dev`, and set
`NEXTAUTH_SECRET` in the **repo-root** `.env` for Compose (same Phase 10 block
as `.env.example`).

### Docker Compose

```bash
docker compose up -d --build dashboard
# http://localhost:3002
```

The dashboard is the browser-facing “reverse proxy” to platform APIs: all
mutations go through `/api/gateway/*` with the user session token / demo API key.

## Tests

```bash
npm test                 # Vitest — Incidents list + auth-gated buttons
npx playwright install chromium
AUTH_DEMO_OFFLINE=true npm run build && npm run test:e2e
```

## Live throughput

Overview embeds `LiveThroughput`, which opens an SSE stream at
`/api/stream/throughput`. That route bridges the gateway’s
`GET /v1/telemetry/stream` (Kafka-backed) into event-rate samples for the
sparkline; if the stream is unavailable it falls back to Prometheus.
