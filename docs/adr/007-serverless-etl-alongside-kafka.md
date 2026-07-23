# ADR 007 — Serverless ETL alongside Kafka / Dagster

**Status:** Accepted  
**Date:** 2026-07  
**Phase:** portfolio / infra demo

## Context

ARGUS’s production spine is already decided: Kafka-compatible bus (Redpanda locally, MSK in AWS), stream QA, Iceberg `fleet.telemetry` with transactional writers, and Dagster for lakehouse asset materialization ([ADR 001](001-kafka-redpanda.md), [ADR 002](002-iceberg-lakehouse.md), [ADR 003](003-dagster-vs-airflow.md)). Separately, hiring and portfolio reviewers often expect fluency with **AWS serverless orchestration** (Lambda container images, Step Functions ASL, EventBridge schedules, SQS DLQs) as shown in hydra-data-factory Phase 9.

We need that demonstration **without** forking the production table or pretending Lambda replaces the streaming path.

## Decision

Ship an additive Terraform module `infra/terraform/modules/serverless-etl/` that:

1. Runs a clearly labeled **demo** pipeline: generate → Pandera validate → sync → DLQ on failure.
2. Writes only under `s3://…/serverless/…` and registers partitions on **`fleet.serverless_batches`**, never `fleet.telemetry` / the Iceberg warehouse prefix.
3. Reuses ARGUS contracts (`validate_telemetry_batch`) and the fleet simulator — same gate as the real path, different sink.
4. Gates EventBridge behind `enable_eventbridge_schedule = false` by default (cost-conscious opt-in).

Kafka/MSK + Dagster remain the production orchestration story. The serverless module is a parallel skill demo and optional batch path.

## Alternatives considered

| Option | Why not |
|--------|---------|
| **Replace Kafka with Step Functions** | Wrong latency/volume model for continuous fleet telemetry; loses replay, consumer groups, and the existing Ray/Flink design |
| **Write serverless output into Iceberg `fleet.telemetry`** | Two writers on one transactional table — catalog/snapshot races and unclear ownership |
| **Omit serverless entirely** | Leaves a gap vs the hydra portfolio narrative for Lambda/SFN/EventBridge/SQS |

## Consequences

- Operators must treat `serverless_batches` as demo/analytics sidecar data, not the source of truth for incidents or the dashboard.
- Image push to ECR is a prerequisite before Lambdas run; Terraform owns the repo (`force_delete = true`) but not the build pipeline.
- Enabling the EventBridge schedule is an explicit cost decision per environment.
