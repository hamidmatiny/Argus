# ARGUS

**ARGUS** is a unified fleet telemetry, data-quality, MLOps, and observability platform: devices stream into a Kafka-compatible bus, Ray and Flink harden the data path, Iceberg + Dagster form the lakehouse spine, and drift / incident / OpenTelemetry layers close the loop for operators — with an AI copilot for query and explanation.

## Architecture

```mermaid
flowchart LR
  Sim["ingestion/simulator"] --> Kafka["Kafka / Redpanda"]
  Devices["Fleet devices / SDKs"] --> Kafka
  Kafka --> Ray["ingestion/ray_consumer"]
  Ray --> Norm["telemetry.normalized"]
  Norm --> QA["stream-processor QA<br/>Flink / local"]
  QA --> Val["telemetry.validated"]
  QA --> Quar["telemetry.quarantine"]
  QA --> Metrics["telemetry.qa_metrics"]
  Val --> Iceberg["Iceberg lakehouse"]
  Quar --> Iceberg
  Val --> Drift["drift-monitor"]
  Iceberg --> Trino["Trino SQL"]
  Iceberg --> Dagster["Dagster orchestration"]
  Drift --> IncRaw["incidents.raw"]
  IncRaw --> Incidents["incident-engine"]
  Incidents --> OTel["observability"]
  OTel --> UI["dashboard"]
  Incidents --> UI
  Iceberg -.-> Copilot["ai-copilot"]
  Incidents -.-> Copilot
  Copilot -.-> UI
```

```text
ingestion/simulator ──► telemetry.raw
fleet devices/SDKs  ──┘       │
                              ▼
              Ray ingestion (DataStreamer actors)
                              │
                              ▼
                    telemetry.normalized
                              │
                              ▼
              stream-processor QA (Flink | local)
                     │            │            │
                     ▼            ▼            ▼
           telemetry.validated  quarantine  qa_metrics
                     │  \         \
                     │   \         └──► lakehouse-dlq-writer → fleet.quarantine
                     │    └──► drift-monitor ──► incidents.raw ──► incident-engine
                     ▼
         lakehouse-writer → fleet.telemetry → Trino / Dagster
                                                              │
                                         observability / dashboard / ai-copilot
```

## Monorepo layout

| Path | Language | Purpose | Stage |
|------|----------|---------|-------|
| `shared/` | Multi | Contracts, schemas, shared libs | Phase 1 |
| `ingestion/` | Python (Ray) | Simulator + Ray consumer (raw → normalized) | Phase 2 |
| `stream-processor/` | Python (PyFlink + local) | QA gate → validated / quarantine / qa_metrics | Phase 3 |
| `drift-monitor/` | Python | KS + Evidently drift on validated → `incidents.raw` | Phase 4 |
| `lakehouse/` | Python + SQL | Iceberg `fleet.telemetry` / `fleet.quarantine` + Trino | Phase 5 |
| `orchestration/` | Python (Dagster) | Assets + MLflow retrain lineage (+ optional Feast) | Phase 6 |
| `incident-engine/` | Go | OPA policies + circuit breaker → `incidents.escalated` | Phase 7 |
| `api-gateway/` | Go | gRPC+REST edge, Keycloak OIDC, OPA RBAC | Phase 9 |
| `observability/` | YAML/+ | Prometheus, Grafana, Loki, Jaeger, Alertmanager | Phase 8 |
| `ai-copilot/` | Python | NL query/explain over platform data | Later |
| `dashboard/` | TypeScript | Operator UI (Next.js) | Phase 10 |
| `sdk/python/` | Python | Client SDK for emitters and APIs | Later |
| `sdk/typescript/` | TypeScript | Client SDK for web/Node | Later |
| `cli/` | Go | Operator CLI (`argusctl`), secrets | Phase 9+ |
| `infra/terraform/` | HCL | Cloud/EKS foundation | Later |
| `infra/helm/` | YAML | Kubernetes charts | Later |
| `infra/argocd/` | YAML | GitOps applications | Later |
| `examples/` | Multi | Sample producers and walkthroughs | Ongoing |
| `docs/` | Markdown | ADRs, runbooks, guides | Ongoing |
| `tests/e2e/` | Multi | Cross-service golden-path tests | Later |

## Quick start (local)

```bash
cp .env.example .env
make up          # Redpanda + Console + simulator + Ray consumer
make logs        # follow compose logs
make down        # tear down
```

See [ARCHITECTURE.md](./ARCHITECTURE.md) for system design and [CONTRIBUTING.md](./CONTRIBUTING.md) for the phase-based build process.

## License

Apache License 2.0 — see [LICENSE](./LICENSE).
