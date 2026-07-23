# Case Study — Building ARGUS

*First-person portfolio write-up. Link this from a resume or personal site.*

## Problem

Modern fleets generate continuous telemetry, but the hard part is not “getting Kafka running.” It is keeping **bad data out of the lake**, detecting **distribution shift before models rot**, turning signals into **actionable incidents with policy**, and giving operators a **single pane** — without bolting five demos together that disagree on schemas.

I wanted a system that a hiring manager could clone, `docker compose up`, and *believe*: same contracts from laptop to EKS, tests and security scanning in CI, and explicit architecture decisions — not a slide deck with a half-working notebook.

## Approach

I built ARGUS as a **phase-gated monorepo** (0–15): each phase shipped a reviewable vertical slice with README, Dockerfile, health endpoints, structured logs, and tests.

Rough sequence:

1. **Contracts first** — Avro/Protobuf/JSON Schema in `shared/`, regenerated stubs, registry registration.
2. **Data plane** — Redpanda → Ray normalize → Flink/local QA → Iceberg (MinIO/REST) + Trino.
3. **MLOps loop** — Dagster assets, MLflow, drift-monitor (KS + Evidently) → `incidents.raw`.
4. **Control plane** — Go incident-engine with OPA + circuit breakers; api-gateway with Keycloak + OPA RBAC.
5. **Human + AI surfaces** — Next.js dashboard; read-only RAG copilot over runbooks and live tools.
6. **Prod path** — Terraform (VPC/EKS/MSK/S3/Glue), Helm, Argo CD; CI with path filters, coverage ≥65%, Trivy, SBOM, nightly e2e/load/chaos.

## Architecture decisions (trade-offs)

| Decision | Chose | Over | Why |
|----------|-------|------|-----|
| Bus | Kafka API (Redpanda / MSK) | Pulsar, NATS, Kinesis-only | One code path; local speed; industry default |
| Lake | Iceberg | Delta, plain Parquet | ACID + time travel + Trino-friendly |
| Orchestration | Dagster | Airflow | Asset lineage for lakehouse/ML |
| Policy | OPA/Rego | Hand-rolled `if` trees | Reviewable escalation + RBAC |
| Copilot | Read-only tools | Write-capable agent | No LLM blast radius on ack/retrain |
| Parity | Compose ≈ Helm images | “Demo rewrite” | Credibility |

Full write-ups: [ADRs](adr/index.md).

## What I’d do differently at 10× scale

- **Partition and shard deliberately** — per-fleet Kafka topics / consumer groups; Ray and Flink autoscaling keyed by tenant.
- **Separate control and data planes in the network** — stricter NetworkPolicies, private MSK, Trino gateway only via gateway with row filters enforced in SQL views.
- **Baseline management** — versioned drift baselines in the lakehouse with approval workflow, not only live windows.
- **Multi-region** — active/passive Iceberg catalogs; incident-engine state in a replicated store instead of process memory for breakers.
- **Cost** — tiered storage for quarantine; sample validated telemetry for drift instead of full firehose where acceptable.
- **Auth** — replace demo API keys with short-lived OIDC + workload identity everywhere (already the prod shape).

## Known gaps (governance & ops maturity)

Scale is only one axis. For deliberate cuts on lineage, secrets backends, audit logs, DR, service mesh,
chaos fault-injection, and FinOps — see **[Known Gaps & What's Deliberately Out of Scope](KNOWN_GAPS.md)**.

## Metrics & footprint (local / repo)

Numbers from the v1.0.0 codebase and laptop compose runs (not a cloud load test):

| Metric | Value |
|--------|-------|
| Compose services | **32** |
| Application Dockerfiles | **11** |
| Helm charts | **9** |
| Terraform `.tf` files | **8** (5 modules + 3 envs) |
| AI runbooks | **5** (also human ops doc) |
| ADRs | **6** |
| CI coverage gate | **≥ 65%** (Python hard; Go gated packages) |
| Copilot eval | **15/15** scenarios with mock LLM (gate ≥ 0.7) |
| Simulator default | **12** vehicles × **~10 Hz** (~120 events/s aggregate) |
| Injected QA failures | **~5%** (`SIMULATOR_FAILURE_RATE`) → quarantine path exercised |
| Nightly e2e | Full compose + **60s** sim + gateway assertions |
| Load gate | k6 gateway ping **p95 &lt; 500ms**, error rate **&lt; 5%** |

Drift detection latency is window-based (warmup + sliding window on validated stream) — typically on the order of **tens of seconds to a few minutes** locally depending on `DRIFT_*` window settings, not sub-second alerting.

## What this demonstrates

- End-to-end **data + ML + ops** thinking, not a single microservice toy
- Comfort with **Python and Go** in one system
- **Policy-as-code**, observability, and supply-chain CI (Trivy/SBOM/SAST)
- Judgment about **AI**: useful for investigation, dangerous for autonomous mutation
- Documentation aimed at **humans with five minutes**, not only future contributors

## Links

- Repo: https://github.com/hamidmatiny/Argus  
- Demo script: [DEMO_SCRIPT.md](DEMO_SCRIPT.md)  
- Known gaps: [KNOWN_GAPS.md](KNOWN_GAPS.md)  
- Architecture: [architecture.md](architecture.md)  
- Changelog: [CHANGELOG](changelog.md) (`v1.0.0`)
