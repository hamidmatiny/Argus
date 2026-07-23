# incident-engine

Go hot-path correlator for ARGUS Phase 7. Consumes QA quarantine metrics and
drift `IncidentEvent`s, evaluates **OPA/Rego** policies, and drives a
per-vehicle **circuit breaker** (`closed → open → half-open`) before
escalating to `incidents.escalated` + Slack/PagerDuty-shaped webhooks.

## Circuit breaker

```text
                 trip (policy)
        ┌──────────────────────────┐
        │                          ▼
   ┌────┴────┐                ┌─────────┐
   │ CLOSED  │ ── trip ─────► │  OPEN   │◄── trip (re-open)
   └────▲────┘                └────┬────┘
        │                          │ OpenCooldown elapsed
        │ success                  ▼
        │                    ┌───────────┐
        └────────────────────│ HALF_OPEN │
                             └───────────┘
```

| State | Behavior |
|-------|----------|
| `closed` | Normal; policy trips transition to `open` and escalate once |
| `open` | Suppress duplicate escalations; after cooldown → `half_open` |
| `half_open` | Probe: healthy evaluation → `closed`; trip → `open` again |

Threshold defaults (sentinel-ray port): rolling quarantine rate **> 15%** over
**5** QA batches, or **≥ 2** drifted features, or **≥ 3** consecutive QA
threshold breaches.

## Shipped Rego policies

| File | Package rule | Trigger |
|------|--------------|---------|
| `policies/quarantine_rate.rego` | `trip_quarantine` | `qa_batch_count >= qa_window_batches` **and** `rolling_quarantine_rate > qa_rate_threshold` (default 0.15 / 5) |
| `policies/drift_count.rego` | `trip_drift` | `drifted_feature_count >= drift_min_features` (default 2) |
| `policies/consecutive_failures.rego` | `trip_consecutive` | `consecutive_failures >= consecutive_failure_max` (default 3) |
| `policies/business_hours_routing.rego` | `route` / `severity` | Mon–Fri 13:00–21:00 UTC → `pagerduty` (or `both` if QA+drift dual signal); else `slack`. Severity `critical` when any trip fires |

## Topics

| Topic | Direction | Payload |
|-------|-----------|---------|
| `telemetry.qa_metrics` | in | per-vehicle quarantine rate windows |
| `incidents.raw` | in | drift-monitor `IncidentEvent` JSON |
| `incidents.escalated` | out | breaker trip + notification channel payloads |

## HTTP API

| Path | Purpose |
|------|---------|
| `GET /health` (`/healthz`) | Liveness |
| `GET /readyz` | Readiness |
| `GET /metrics` | Prometheus (breaker state, incidents processed, policy latency) |
| `GET /breakers` | All vehicle breaker snapshots |
| `GET /incidents?status=open\|resolved` | In-memory escalations (dashboard Phase 10) |
| `POST /incidents/{id}/acknowledge` | Mark open incident acknowledged (still open) |
| `POST /incidents/{id}/resolve` | Manual operator resolve (idempotent) |
| `POST /webhooks/mock` | Local mock receiver (used when no real webhook URLs set) |
| `GET /webhooks/mock/inbox` | Inspect mock deliveries |

Incidents auto-resolve when a vehicle breaker recovers (`half_open` → `closed`). HalfOpen→Open retrips refresh the same open incident (same `incident_id` / PagerDuty `dedup_key`); a new id is minted only after resolution.

## Configuration

| Env | Default | Meaning |
|-----|---------|---------|
| `INCIDENT_ENGINE_ADDR` | `:8098` | HTTP listen |
| `KAFKA_BROKERS` | `localhost:19092` | Redpanda |
| `INCIDENT_ENGINE_KAFKA_GROUP_ID` | `argus-incident-engine` | Consumer group prefix |
| `QA_METRICS_TOPIC` | `telemetry.qa_metrics` | Input |
| `INCIDENTS_RAW_TOPIC` | `incidents.raw` | Input |
| `INCIDENTS_ESCALATED_TOPIC` | `incidents.escalated` | Output |
| `INCIDENT_POLICY_DIR` | `policies` | Rego directory |
| `INCIDENT_QA_WINDOW_BATCHES` | `5` | Rolling QA window |
| `INCIDENT_QA_RATE_THRESHOLD` | `0.15` | Quarantine rate trip |
| `INCIDENT_DRIFT_MIN_FEATURES` | `2` | Drift trip |
| `INCIDENT_CONSECUTIVE_FAILURES` | `3` | Consecutive exceeded batches |
| `INCIDENT_OPEN_COOLDOWN_SEC` | `60` | Open → half-open |
| `INCIDENT_SLACK_WEBHOOK_URL` | _(empty)_ | Optional real Slack |
| `INCIDENT_PAGERDUTY_WEBHOOK_URL` | _(empty)_ | Optional PD Events API |
| `INCIDENT_ENABLE_MOCK_WEBHOOK` | `true` | Loopback mock when URLs empty |

## Run

```bash
# unit tests (state machine + each Rego policy via OPA Go SDK)
cd incident-engine && go test ./...

# compose
docker compose up -d --build incident-engine
curl -s localhost:8098/health | jq .
curl -s localhost:8098/breakers | jq .
curl -s 'localhost:8098/incidents?status=open' | jq .
curl -s localhost:8098/webhooks/mock/inbox | jq .
```

## Layout

```text
cmd/incident-engine/     entrypoint
internal/circuitbreaker/ FSM + store
internal/policy/         OPA loader + eval
internal/engine/         Kafka correlation
internal/webhook/        Slack/PD payloads + dispatcher
internal/api/            REST + mock webhook
internal/kafka/          segmentio consumers/producer
internal/metrics/        Prometheus
policies/                *.rego
```
