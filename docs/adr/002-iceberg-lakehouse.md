# ADR 002 — Apache Iceberg lakehouse

**Status:** Accepted  
**Date:** 2026-07  
**Phase:** 5

## Context

Validated telemetry and quarantine need ACID tables, partition evolution, and engine-agnostic SQL (Trino today, Spark/Flink later). Alternatives: Delta Lake, Apache Hudi, or raw Hive-style Parquet folders.

## Decision

Use **Apache Iceberg** with:

- Local: REST catalog + MinIO (S3 API)
- Prod: Glue Data Catalog + S3 (Terraform module)

Tables: `fleet.telemetry`, `fleet.quarantine`.

## Alternatives considered

| Option | Trade-off |
|--------|-----------|
| **Delta Lake** | Excellent on Databricks/Spark; more Spark-centric than we wanted for Trino-first demos |
| **Hudi** | Strong upserts/incremental; Iceberg ecosystem + Trino support preferred here |
| **Plain Parquet** | No snapshots, time travel, or safe concurrent writers — fails ops/ML trust goals |

## Consequences

- Writers must speak Iceberg correctly (partition by `device_type` + day).
- Time travel and schema evolution become first-class for incident forensics.
- Local MinIO + REST catalog keeps laptop demos free of AWS accounts.
