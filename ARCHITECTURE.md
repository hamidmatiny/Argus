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
| **ingestion (Ray)** | Scale-out consume/normalize; batch toward QA and lakehouse writers |
| **stream-processor (Flink)** | Streaming QA gate: schema, ranges, freshness, quarantine |
| **lakehouse (Iceberg)** | Bronze → silver → gold tables; time travel; compaction |
| **orchestration (Dagster)** | Assets, schedules, sensors; ties lakehouse to ML and drift jobs |
| **drift-monitor** | Compare live vs baseline distributions; emit drift signals |
| **incident-engine** | Correlate QA/drift/SLO signals into incidents |
| **api-gateway** | Authn/authz (OPA), rate limits, north-south API surface |
| **observability** | OTel collection, metrics/traces/logs, SLOs and alerts |
| **dashboard** | Human ops surface for health, incidents, and drill-down |
| **ai-copilot** | Query/explain layer over governed APIs and metadata (not on the hot write path) |
| **cli** | Operator tooling against the gateway |

## Data flow

1. Devices (or `sdk/*`) publish to Kafka topics (`telemetry.raw.*`).
2. Ray ingestion consumes, normalizes, and republishes / writes toward Flink and bronze landing.
3. Flink QA enforces contracts; failures go to quarantine topics; passes land in Iceberg bronze/silver.
4. Dagster materializes gold assets, training/eval jobs, and triggers drift evaluations.
5. drift-monitor writes findings; incident-engine correlates with QA and SLO breaches.
6. Observability scrapes/receives OTel; dashboard and ai-copilot read via api-gateway.

```text
[devices] → [Kafka] → [Ray] → [Flink QA] → [Iceberg]
                                              ↓
                                         [Dagster]
                                              ↓
                                       [drift-monitor]
                                              ↓
                                      [incident-engine]
                                         ↙         ↘
                              [observability]    [dashboard]
                                         ↖         ↗
                                          [ai-copilot]
```

## Data contracts

Contracts live under `shared/` (schemas evolve in Phase 1+). Design principles:

- **Envelope**: every event has `event_id`, `device_id`, `schema_version`, `event_time`, `ingest_time`, `payload`.
- **Versioned schemas**: Avro or Protobuf + JSON Schema for API edges; incompatible changes require a new major `schema_version`.
- **Topics**: `telemetry.raw.<domain>`, `telemetry.quarantine.<domain>`, `telemetry.clean.<domain>`, `signals.drift`, `signals.incidents`.
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
- **Phase 0:** Redpanda only (Kafka-compatible broker)
- **Later phases:** add services as commented placeholders in `docker-compose.yml` (ingestion, Flink, lakehouse deps, Dagster, drift, incident-engine, gateway, OTel, dashboard, copilot)
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
