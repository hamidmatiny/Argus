# Known Gaps & What's Deliberately Out of Scope

This page is the **governance / compliance / operational-maturity** axis — not the scale axis.
Scale items (partitioning, multi-region Iceberg, tiered storage, OIDC everywhere) live in the case study’s
[“What I’d do differently at 10× scale”](CASE_STUDY.md) section.
The gaps below are intentional portfolio cuts: naming what exists today versus what a real production
deployment would still need.

## Data governance & lineage

Today Dagster’s asset graph and MLflow run params give *coarse* lineage (retrain decisions, report paths),
but there is **no column-level lineage** across Kafka topics → Iceberg snapshots → Dagster materializations →
MLflow model versions. A production platform would add OpenLineage/Marquez (or fully surface Dagster asset
lineage + Iceberg snapshot IDs) so “which model trained on which data snapshot” is answerable under audit.

## Secrets management

`argusctl secrets` plus `.env` / Compose env files are the right shape for local and portfolio demos.
Production would back the same interfaces with **Vault or AWS Secrets Manager** (rotation, least-privilege
IAM, no long-lived secrets on disk) — a deliberate scope cut, not an oversight of how secrets should work.

## Audit trail

OPA already enforces **viewer / operator / admin** RBAC on gateway and incident actions, but there is no
**immutable audit log** of who acknowledged an incident, who triggered a retrain, or who changed a Rego
policy. SOC2-style compliance needs append-only, queryable records of those mutations.

## Disaster recovery

There is no documented backup/restore runbook for Postgres-backed **MLflow/Dagster** state, the **Iceberg
catalog** (REST/Glue), or **Kafka/MSK topic replay**. A real DR plan would set RPO/RTO targets, scheduled
catalog + DB backups, retention for compacted topics / Iceberg snapshots, and a restore drill cadence —
none of which are claimed here.

## Service mesh / zero-trust

Helm charts ship real Kubernetes **NetworkPolicies**, which constrain east-west traffic at L3/L4.
There is no **mTLS / service-identity** layer (Istio or Linkerd) proving workload identity between
simulator, Ray, gateway, and incident-engine — NetworkPolicy alone is not zero-trust.

## Chaos engineering

Phase 14’s nightly path includes **k6 load** and compose smoke, and the incident-engine has unit-tested
circuit breakers under synthetic drift/incident inputs. There is no **Chaos Mesh / Litmus** (or equivalent)
fault injection against pod kill, network partition, or broker loss to prove those breakers under real
infrastructure failure.

## FinOps

Terraform and Helm apply default tags (`Project`, `Environment`, `ManagedBy`), but there is no
**cost-allocation tagging strategy**, budget alarms, or spend dashboards tied to MSK / EKS / S3.
That remains a trackable concern for any real cloud bill; it is simply not instrumented in this repo.
