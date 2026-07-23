# api-gateway

Governed north-south edge for ARGUS (Phase 9). External clients (dashboard,
SDKs, `curl`) hit this service only — never Trino / Dagster / incident-engine
directly.

**Stack:** gRPC (`GatewayService`) + grpc-gateway REST/JSON · Keycloak OIDC
JWT AuthN · OPA/Rego AuthZ (`viewer` / `operator` / `admin`) · token-bucket
rate limits · OpenTelemetry (`traceparent`) · Prometheus `/metrics`.

## What it does

See the narrative sections below for responsibilities and scope.

## Quick start

```bash
# From repo root
docker compose up -d --build
```

## Ports

| Port | Protocol | Purpose |
|------|----------|---------|
| `8099` | HTTP | REST (grpc-gateway), `/health`, `/metrics`, `/openapi.json` |
| `9099` | gRPC | Native gRPC + reflection (`grpcurl`) |
| `8085` | HTTP | Keycloak (host) → container `:8080` |

## Endpoints (REST)

| Method | Path | Role | Upstream |
|--------|------|------|----------|
| `GET` | `/health`, `/healthz`, `/readyz` | public | — |
| `GET` | `/metrics` | public | — |
| `GET` | `/openapi.json` | public | generated swagger |
| `GET` | `/v1/ping` | public | traced ping |
| `POST` | `/v1/telemetry/query` | viewer+ | Trino SQL |
| `GET` | `/v1/telemetry/stream` | viewer+ | Kafka `telemetry.validated` (SSE/chunked via gateway) |
| `GET` | `/v1/incidents?status=` | viewer+ | incident-engine |
| `POST` | `/v1/incidents/{id}/acknowledge` | operator+ | incident-engine |
| `POST` | `/v1/retraining:trigger` | operator+ | Dagster GraphQL `launchRun` |

gRPC methods mirror the same RPCs on `argus.v1.GatewayService`
(see `shared/proto/argus/v1/gateway.proto`).

## Auth flow

```text
Browser / SDK
   │  password grant (demo) or auth code
   ▼
Keycloak realm `argus`  (:8085)
   │  JWT (RS256) with realm roles: viewer|operator|admin
   ▼
api-gateway
   ├─ rate limit (X-API-Key or token prefix)
   ├─ JWT validate (JWKS)  OR  X-API-Key → role map
   ├─ OPA allow(role, method, path)
   └─ proxy / stream
```

### Pre-provisioned Keycloak users

| User | Password | Roles |
|------|----------|-------|
| `viewer` | `viewer` | viewer |
| `operator` | `operator` | operator, viewer |
| `admin` | `admin` | admin, operator, viewer |

Client id: `argus-gateway` (public, direct access grants enabled for local demos).

### Demo API keys (compose default)

| Key | Role |
|-----|------|
| `demo-viewer` | viewer |
| `demo-operator` | operator |
| `demo-admin` | admin |

Set `API_GATEWAY_AUTH_DISABLED=true` to skip JWT (inject role with `X-Argus-Role`).

## Example: curl

```bash
# 1) Get a token from Keycloak
TOKEN=$(curl -s -X POST 'http://localhost:8085/realms/argus/protocol/openid-connect/token' \
  -d 'client_id=argus-gateway' \
  -d 'username=operator' \
  -d 'password=operator' \
  -d 'grant_type=password' | jq -r .access_token)

# 2) List incidents
curl -s http://localhost:8099/v1/incidents \
  -H "Authorization: Bearer $TOKEN" | jq .

# 3) Query telemetry via Trino
curl -s http://localhost:8099/v1/telemetry/query \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"sql":"SELECT vehicle_id, speed_mph FROM telemetry LIMIT 5","limit":5}' | jq .

# 4) Acknowledge an incident (operator+)
curl -s -X POST http://localhost:8099/v1/incidents/INCIDENT_ID/acknowledge \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"note":"investigating"}' | jq .

# 5) Trigger Dagster retraining (operator+)
curl -s -X POST http://localhost:8099/v1/retraining:trigger \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"reason":"manual demo","tags":{"ticket":"DEMO-1"}}' | jq .

# API key shortcut (no Keycloak)
curl -s http://localhost:8099/v1/incidents -H 'X-API-Key: demo-viewer' | jq .
```

## Example: grpcurl

```bash
# List services
grpcurl -plaintext localhost:9099 list

# List incidents (pass bearer via metadata)
grpcurl -plaintext \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"status":"open"}' \
  localhost:9099 argus.v1.GatewayService/ListIncidents
```

> Note: AuthZ middleware is applied on the **HTTP** surface. For local gRPC
> demos against `:9099`, prefer REST or run with `API_GATEWAY_AUTH_DISABLED=true`
> when exercising grpcurl directly.

## OpenAPI

```bash
curl -s http://localhost:8099/openapi.json | jq '.info'
```

Generated from grpc-gateway annotations (`make proto` →
`shared/gen/openapi/argus/v1/gateway.swagger.json`, copied into
`api-gateway/openapi/` for the image).

## OPA roles (`policies/gateway.rego`)

| Role | Allowed |
|------|---------|
| `viewer` | GET `/v1/*`, POST `/v1/telemetry/query` |
| `operator` | viewer + acknowledge + trigger retraining |
| `admin` | all `/v1/*` |

## Configuration

| Env | Default | Meaning |
|-----|---------|---------|
| `API_GATEWAY_ADDR` | `:8099` | HTTP listen |
| `API_GATEWAY_GRPC_ADDR` | `:9099` | gRPC listen |
| `API_GATEWAY_AUTH_DISABLED` | `false` | Dev bypass |
| `OIDC_ISSUER_URL` | `http://localhost:8085/realms/argus` | JWT `iss` |
| `OIDC_JWKS_URL` | `http://keycloak:8080/.../certs` | JWKS fetch |
| `OIDC_AUDIENCE` | `argus-gateway` | JWT aud/azp |
| `INCIDENT_ENGINE_URL` | `http://incident-engine:8098` | Incidents proxy |
| `TRINO_URL` | `http://trino:8080` | SQL proxy |
| `DAGSTER_GRAPHQL_URL` | `http://dagster-webserver:3000/graphql` | Retrain |
| `KAFKA_BROKERS` | `redpanda:9092` | Live stream |
| `API_GATEWAY_RATE_LIMIT_RPS` | `20` | Token bucket refill |
| `API_GATEWAY_API_KEYS` | `demo-*:role` | Key → role map |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | `http://otel-collector:4318` | Traces |

## Tests

```bash
cd api-gateway && go test ./...
```

- Middleware: missing bearer → 401, viewer denied on retrain → 403, rate limit → 429
- OPA unit matrix for roles
- Integration: mocked Trino / incident-engine / Dagster for each proxied REST route

## Layout

```text
api-gateway/
  cmd/api-gateway/     entrypoint
  internal/
    auth/              OIDC JWT validation
    authz/             OPA loader (incident-engine pattern)
    ratelimit/         per-key token bucket
    middleware/        AuthN/AuthZ/rate-limit/logging/metrics
    upstream/          Trino, incidents, Dagster, Kafka stream
    service/           GatewayService implementation
    server/            gRPC + grpc-gateway HTTP
  policies/            gateway.rego
  keycloak/            realm import for compose
  openapi/             swagger served at /openapi.json
```