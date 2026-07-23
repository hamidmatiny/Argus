# observability

Platform-grade metrics, logs, traces, and alerting for ARGUS — Prometheus,
Grafana, Loki/Promtail, Jaeger, OpenTelemetry Collector, Alertmanager, and a
lightweight on-call report generator.

**Status:** Phase 8 — wired into `docker-compose.yml`.

## Ports (host)

| Service | Port | Notes |
|---------|------|-------|
| Prometheus | [9090](http://localhost:9090) | Targets + graph |
| Grafana | [3001](http://localhost:3001) | admin / `argus` (anon Viewer on) |
| Alertmanager | [9093](http://localhost:9093) | Routing UI |
| Loki | [3100](http://localhost:3100/ready) | Log store |
| Jaeger UI | [16686](http://localhost:16686) | Trace search |
| OTel Collector | 4317 (gRPC), 4318 (HTTP) | App OTLP export |
| On-call reporter | [8100](http://localhost:8100/report) | Printed incident report |
| api-gateway stub | [8099](http://localhost:8099/v1/ping) | Traced ping |

## Scraped services (`service` label)

| Job | Target | Metrics |
|-----|--------|---------|
| simulator | `:8091/metrics` | `argus_ingestion_*` |
| ray-consumer | `:8092/metrics` | `argus_ingestion_*` |
| stream-processor | `:8093/metrics` | `argus_qa_*` |
| drift-monitor | `:8095/metrics` | `argus_drift_*` |
| lakehouse-writer | `:8096/metrics` | `argus_lakehouse_*` |
| lakehouse-dlq-writer | `:8097/metrics` | `argus_lakehouse_*` |
| incident-engine | `:8098/metrics` | `argus_incident_*` |
| api-gateway | `:8099/metrics` | `argus_gateway_*` |

## Recording rules (`prometheus/rules/slo.yml`)

| Rule | Purpose |
|------|---------|
| `argus:ingestion_events_per_second` | Ingestion throughput |
| `argus:qa_pass_ratio` | Validated / (validated + quarantined) |
| `argus:drift_score_avg` | Mean feature drift |
| `argus:breaker_trip_rate` | Escalation publish rate |
| `argus:breakers_open` | Count of open breakers |
| `argus:retraining_trigger_rate` | Escalation proxy until Dagster exports |

## Alert rules → Alertmanager routes

| Alert | Severity | Channel | Receiver |
|-------|----------|---------|----------|
| `CircuitBreakerOpen` | critical | incidents | `incident-engine` mock webhook `:8098/webhooks/mock` |
| `EscalationStorm` | critical | incidents | same |
| `QAPassRateSLOBreach` | warning | drift | `oncall-reporter` `/webhook/drift` |
| `DriftScoreElevated` | warning | drift | same |

Default unmatched alerts → `oncall-reporter` `/webhook/default`.

## Grafana dashboards (auto-provisioned)

1. **Fleet Ingestion Overview** (`argus-fleet-ingestion`) — throughput, QA SLO, target `up`, gateway RPS
2. **Data Quality & Drift** (`argus-data-quality-drift`) — 99% QA gauge, per-feature drift, baseline staleness
3. **Incidents & Circuit Breakers** (`argus-incidents-breakers`) — open breakers, trip rate, policy latency

Datasources: Prometheus (default), Loki, Jaeger.

## Traces (OpenTelemetry → Collector → Jaeger)

Instrumented today:

- **api-gateway** — HTTP middleware + `/v1/ping` span
- **stream-processor** — QA validate spans (when `OTEL_EXPORTER_OTLP_ENDPOINT` is set)

Apps export OTLP/HTTP to `http://otel-collector:4318`; collector forwards to Jaeger.

## Logs (Loki + Promtail)

Promtail discovers Docker containers via the socket, labels by compose `service`,
and ships stdout/stderr to Loki. Structured JSON fields (`level`, `msg`, `logger`)
are promoted to Loki labels when present. Query in Grafana **Explore → Loki**, e.g.:

```logql
{compose_project="argus", service="incident-engine"} |= "escalat"
```

Promtail is filtered to `com.docker.compose.project=argus` so sibling compose stacks on the same Docker host are ignored.

## On-call report

```bash
curl -s localhost:8100/report
```

Prints an SLO snapshot, vanguard-style breach evaluation, recent Alertmanager
webhooks, and a tail of the incident-engine mock inbox.

## How to demo observability in 2 minutes

1. **Open Grafana** → http://localhost:3001 → dashboard **Fleet Ingestion Overview**.
   Point at **QA pass ratio (SLO ≥ 99%)** (green when healthy) and **Ingestion throughput**.

2. **Inject failure** — raise quarantine / bad telemetry for ~2 minutes:
   ```bash
   # bump simulator failure rate (restart simulator with higher rate)
   docker compose up -d --force-recreate simulator \
     -e SIMULATOR_FAILURE_RATE=0.35
   ```
   Or wait for a live breaker trip: open **Incidents & Circuit Breakers** and watch
   **Open circuit breakers** / per-vehicle state flip to `2`.

3. **Show the chain**
   - Grafana **Data Quality & Drift** — QA gauge turns yellow/red under 99%; drift panels move.
   - Alertmanager http://localhost:9093 — `QAPassRateSLOBreach` (warning) and/or `CircuitBreakerOpen` (critical).
   - Critical path: `curl -s localhost:8098/webhooks/mock/inbox | jq .` shows Alertmanager payloads.
   - Warning path: `curl -s localhost:8100/alerts | jq .` and `curl -s localhost:8100/report`.

4. **Traces** — `curl -s localhost:8099/v1/ping` then open Jaeger http://localhost:16686 →
   service `api-gateway` → find the `ping` span. Stream-processor spans appear under
   `stream-processor` while QA is processing.

5. **Logs** — Grafana Explore → Loki → `{compose_project="argus"}` or `{service="stream-processor"}`.

## Layout

```text
observability/
  prometheus/          scrape + recording/alert rules
  alertmanager/        severity routing
  grafana/provisioning datasources + dashboards
  loki/                single-node Loki
  promtail/            Docker log shipper
  otel/                Collector → Jaeger
  oncall/              webhook sink + printable report
```
