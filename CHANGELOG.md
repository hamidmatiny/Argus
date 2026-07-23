# Changelog

All notable changes to ARGUS are documented here.

## [v1.0.0] — 2026-07-23

First production-shaped release of the ARGUS monorepo (Phases 0–15).

### Platform

- End-to-end fleet telemetry path: Redpanda → Ray → QA → Iceberg/Trino → drift → OPA incidents → gateway → dashboard / copilot
- Local docker compose (**32** services) with image/config parity toward EKS
- Contract-first `shared/` (Avro, Protobuf, JSON Schema) with registry helpers

### Phases (summary)

| Phase | Delivered |
|-------|-----------|
| **0** | Monorepo scaffold, compose Redpanda, Makefile, CI skeleton, Go workspace |
| **1** | Shared contracts, `make proto` / contracts tests, topic naming |
| **2** | Ingestion simulator + Ray consumer (`telemetry.raw` → `normalized`) |
| **3** | stream-processor QA (local + Flink option), quarantine + qa_metrics |
| **4** | drift-monitor (KS, embeddings, Evidently) → `incidents.raw` |
| **5** | Iceberg lakehouse writers, MinIO/REST catalog, Trino |
| **6** | Dagster orchestration, MLflow retrain lineage, optional Feast |
| **7** | incident-engine (Go): OPA policies, circuit breakers, webhooks |
| **8** | Observability stack (Prometheus, Grafana, Loki, Jaeger, OTel, alerts) |
| **9** | api-gateway (Go): OIDC/Keycloak, OPA RBAC, REST/gRPC, rate limits |
| **10** | Next.js operator dashboard (Overview, Incidents, DQ, Telemetry, Pipeline) |
| **11** | Python + TypeScript SDKs, `argusctl` CLI, fleet-dispatcher example |
| **12** | Terraform (VPC/EKS/MSK/Iceberg), Helm charts, Argo CD app-of-apps |
| **13** | ai-copilot: Qdrant RAG, read-only tools, guardrails, eval harness |
| **14** | Multi-job CI, Docker+Trivy+SBOM, Semgrep, e2e/load/chaos nightlies |
| **15** | MkDocs Material docs, ADRs, demo script, case study, README polish |

### Quality & security

- Path-filtered CI with **≥65%** coverage gates
- Container builds with `/health` smoke, Trivy HIGH/CRITICAL, Syft SBOM
- Semgrep SAST; nightly full-stack smoke, k6 load SLO, chaos recovery

### Docs

- MkDocs Material site under `docs/` (`mkdocs.yml`)
- ADRs 001–006, operations runbook, `DEMO_SCRIPT.md`, `CASE_STUDY.md`

### Upgrade notes

- Copy `.env.example` → `.env` and set `NEXTAUTH_SECRET` before `docker compose up`
- Default LLM is `mock` for offline demos; set provider keys via `argusctl secrets` for real models
