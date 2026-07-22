# ARGUS Architecture

This document describes the system design for ARGUS: responsibilities, data contracts, technology choices, and deployment topology. Implementation lands phase-by-phase; this file is the north-star design.

## Goals

- **Unified plane** for fleet telemetry, data quality, MLOps, and ops observability
- **Contract-first** ingestion so bad data is quarantined early
- **Lakehouse spine** (Iceberg) that both analytics and ML can trust
- **Closed loop** from drift → incidents → dashboards / copilot
- **Same contracts** locally (docker compose) and in production (EKS + GitOps)

## Component responsibilities

| Component | Responsibility |
|-----------|----------------|
| **Fleet devices / SDKs** | Emit typed telemetry events (metrics, logs, edge features) to Kafka topics |
| **Kafka / Redpanda** | Durable, ordered bus between producers and processors |
| **ingestion (Ray)** | Simulator publishes Avro to `telemetry.raw`; Ray DataStreamer actors normalize to `telemetry.normalized` |
| **stream-processor (Flink / local)** | Streaming QA gate: Pandera-equivalent checks → `telemetry.validated` / `telemetry.quarantine` / `telemetry.qa_metrics` |
| **lakehouse (Iceberg)** | Kafka → Iceberg (`fleet.telemetry`, `fleet.quarantine`) via REST/Glue + MinIO/S3; Trino SQL |
| **orchestration (Dagster)** | Assets, schedules, sensors; ties lakehouse to ML and drift jobs |
| **drift-monitor** | KS + embedding + Evidently on `telemetry.validated`; publish `IncidentEvent` to `incidents.raw` |
| **incident-engine** | Correlate QA/drift/SLO signals into incidents |
| **api-gateway** | Authn/authz (OPA), rate limits, north-south API surface |
| **observability** | OTel collection, metrics/traces/logs, SLOs and alerts |
| **dashboard** | Human ops surface for health, incidents, and drill-down |
| **ai-copilot** | Query/explain layer over governed APIs and metadata (not on the hot write path) |
| **cli** | Operator tooling against the gateway |

## Data flow

1. `ingestion/simulator` (or devices / `sdk/*`) publish to Kafka topic `telemetry.raw`.
2. Ray ingestion (`DataStreamer` actor pool) consumes, normalizes, and republishes to `telemetry.normalized`.
3. `stream-processor` QA gate (PyFlink or `--engine=local`) validates each record:
   - pass → `telemetry.validated`
   - fail → `telemetry.quarantine` (structured DLQ: field, rule, raw payload)
   - tumbling per-vehicle quarantine rate → `telemetry.qa_metrics`
4. `lakehouse-writer` appends `telemetry.validated` to Iceberg `fleet.telemetry` (partitioned by `device_type` + day); `lakehouse-dlq-writer` archives `telemetry.quarantine` to `fleet.quarantine`. Query via Trino. Dagster (later) materializes gold assets and ML jobs.
5. `drift-monitor` consumes `telemetry.validated` in parallel (KS/Evidently vs golden baseline) and publishes `IncidentEvent` to `incidents.raw` when ≥ N features drift; incident-engine correlates with QA metrics and SLO breaches.
6. Observability scrapes/receives OTel; dashboard and ai-copilot read via api-gateway.

```text
[devices/simulator] → telemetry.raw → [Ray] → telemetry.normalized
                                                    │
                                                    ▼
                                          [stream-processor QA]
                                           /        |         \
                                          v         v          v
                                   validated   quarantine   qa_metrics
                                    /    |  \         \
                                   /     |   \         └──► [dlq-writer] → fleet.quarantine
                                  v      |    v
                    [lakehouse-writer]   |  [drift-monitor] → incidents.raw
                            │            |                         │
                            v            |                         v
                     fleet.telemetry     |                  [incident-engine]
                            │            |
                         [Trino] ←——— Iceberg REST + MinIO/S3
                            │
                         [Dagster]
                                                          ↙         ↘
                                               [observability]   [dashboard]
                                                          ↖         ↗
                                                           [ai-copilot]
```

## Data contracts

Contracts live under `shared/` (schemas evolve in Phase 1+). Design principles:

- **Envelope**: every event has `event_id`, `device_id`, `schema_version`, `event_time`, `ingest_time`, `payload`.
- **Versioned schemas**: Avro or Protobuf + JSON Schema for API edges; incompatible changes require a new major `schema_version`.
- **Topics**: `telemetry.raw`, `telemetry.normalized`, `telemetry.validated`, `telemetry.quarantine`, `telemetry.qa_metrics`, `incidents.raw` (drift / future correlators).
- **Iceberg**: bronze = raw-ish append; silver = validated/typed; gold = aggregates and feature tables for ML.
- **API errors**: structured JSON problem details from api-gateway; no free-form strings as the sole error channel.

Exact IDL files are intentionally deferred to Phase 1 (`make proto` will generate stubs).

## Why these technologies

| Choice | Why | Alternatives considered |
|--------|-----|-------------------------|
| **Kafka API (Redpanda local)** | Industry-standard bus; Redpanda avoids ZK pain in local/dev | Pulsar (heavier ops), NATS (great for light events, weaker for large fan-in telemetry archives), cloud-only buses (lock-in for portfolio clarity) |
| **Iceberg** | ACID tables, time travel, engine-agnostic lakehouse | Delta (strong but more Spark-centric), Hudi (great upserts; Iceberg ecosystem fit preferred here), plain Parquet folders (no governance) |
| **Flink** | True streaming QA with event time and exactly-once sinks | Spark Structured Streaming (micro-batch bias), Kafka Streams (JVM-centric, less lakehouse sink ecosystem for this stack) |
| **Ray** | Elastic Python ingest/feature compute without standing up a second Spark cluster for every job | Spark-only (heavier for mixed ML), plain consumers (don’t scale as cleanly for bursty fleets) |
| **Dagster** | Asset-oriented orchestration with strong typing and observability | Airflow (task-first), Prefect (lighter but less lakehouse-native asset model for this design) |
| **MLflow** | Pragmatic model registry + experiment tracking | Weights & Biases (SaaS-first), custom registries (undifferentiated) |
| **OPA** | Policy-as-code for gateway and data access decisions | Homegrown RBAC (doesn’t scale), cloud IAM alone (doesn’t cover app-level row/column policies) |
| **OpenTelemetry** | Vendor-neutral traces/metrics/logs | Vendor agents only (lock-in), ad-hoc statsd (no traces) |

## Local development vs production

### Local (docker compose)

- **Entry point:** `make up` → `docker compose up -d --build`
- **Phase 0–1:** Redpanda + Schema Registry / Console
- **Phase 2:** `simulator` + `ray-consumer` (see `ingestion/`)
- **Phase 3:** Flink JobManager/TaskManager + `stream-processor` QA gate
- **Later phases:** lakehouse deps, Dagster, drift, incident-engine, gateway, OTel, dashboard, copilot (placeholders in compose)
- **Goal:** a laptop-friendly golden path that exercises contracts without cloud accounts

### Production (Terraform + EKS + Helm + Argo CD)

- **Terraform (`infra/terraform`)**: VPC, EKS, IAM/IRSA, object storage, managed Kafka-compatible or self-managed on K8s, observability backends
- **Helm (`infra/helm`)**: per-service charts, probes, resources, OTel annotations
- **Argo CD (`infra/argocd`)**: GitOps sync, environment promotion, drift detection of desired state
- **Parity rule:** same images and config shape as compose; only infrastructure and scale differ

## Non-goals (for now)

- Multi-cloud abstraction layers beyond what’s needed for a clear portfolio architecture
- Replacing every vendor tool; ARGUS is an integration platform, not a greenfield database
- Business logic in Phase 0 — this repo starts as scaffolding only

## Related docs

- [README.md](./README.md) — pitch and layout table
- [CONTRIBUTING.md](./CONTRIBUTING.md) — phase-based contribution model
- `docs/` — ADRs and runbooks (as they land)
