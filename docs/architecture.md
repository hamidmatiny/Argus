# Architecture

North-star design for ARGUS. Implementation lives in component directories; this page is the map.

## Goals

- **Unified plane** for fleet telemetry, data quality, MLOps, and ops observability
- **Contract-first** ingestion so bad data is quarantined early
- **Lakehouse spine** (Iceberg) that analytics and ML can trust
- **Closed loop** from drift → incidents → dashboards / copilot
- **Same contracts** locally (docker compose) and in production (EKS + GitOps)

## System diagram

```mermaid
flowchart LR
  Sim["ingestion/simulator"] --> Kafka["Kafka / Redpanda"]
  Devices["Fleet devices / SDKs"] --> Kafka
  Kafka --> Ray["ingestion/ray_consumer"]
  Ray --> Norm["telemetry.normalized"]
  Norm --> QA["stream-processor QA"]
  QA --> Val["telemetry.validated"]
  QA --> Quar["telemetry.quarantine"]
  QA --> Metrics["telemetry.qa_metrics"]
  Val --> Iceberg["Iceberg lakehouse"]
  Quar --> Iceberg
  Val --> Drift["drift-monitor"]
  Iceberg --> Trino["Trino SQL"]
  Iceberg --> Dagster["Dagster orchestration"]
  Drift --> IncRaw["incidents.raw"]
  IncRaw --> Incidents["incident-engine + OPA"]
  Incidents --> OTel["observability"]
  OTel --> UI["dashboard"]
  Incidents --> UI
  Iceberg -.-> Copilot["ai-copilot"]
  Incidents -.-> Copilot
  Copilot -.-> UI
  UI --> GW["api-gateway"]
  GW --> Trino
  GW --> Incidents
```

## Data flow (ASCII)

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

## Component responsibilities

| Component | Responsibility |
|-----------|----------------|
| Fleet devices / SDKs | Emit typed telemetry to Kafka |
| Kafka / Redpanda | Durable ordered bus |
| ingestion (Ray) | Normalize `telemetry.raw` → `telemetry.normalized` |
| stream-processor | Streaming QA → validated / quarantine / qa_metrics |
| lakehouse (Iceberg) | Append + Trino SQL |
| orchestration (Dagster) | Assets, Evidently → MLflow, retrain events |
| drift-monitor | KS + Evidently → `incidents.raw` |
| incident-engine | OPA + circuit breaker → escalated incidents |
| api-gateway | Authn/authz, north-south API |
| observability | Metrics, logs, traces, SLOs |
| dashboard | Human ops UI |
| ai-copilot | Read-only RAG + tools over governed APIs |
| cli | Operator tooling (`argusctl`) |

## Local vs production

```mermaid
flowchart TB
  subgraph local [Local laptop]
    DC[docker compose]
    RP[Redpanda]
    MINIO[MinIO + Iceberg REST]
    DC --> RP
    DC --> MINIO
  end
  subgraph prod [Production AWS]
    TF[Terraform VPC/EKS/MSK/S3]
    HELM[Helm charts]
    ARGO[Argo CD app-of-apps]
    TF --> HELM --> ARGO
  end
  local -. same images / contracts .-> prod
```

**Parity rule:** same container images and config shape; only infrastructure and scale differ.

## Further reading

- Root [ARCHITECTURE.md](https://github.com/hamidmatiny/Argus/blob/main/ARCHITECTURE.md)
- [ADRs](adr/index.md) for technology trade-offs
- [Components](components/index.md) for per-service deep links
