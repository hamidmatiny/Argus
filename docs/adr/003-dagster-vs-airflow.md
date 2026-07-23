# ADR 003 — Dagster over Airflow for orchestration

**Status:** Accepted  
**Date:** 2026-07  
**Phase:** 6

## Context

Lakehouse assets (feature stats, quarantine audit, Evidently → MLflow retrain signals) need scheduled materialization with clear lineage. Classic choice: Airflow vs Dagster vs Prefect.

## Decision

Use **Dagster** (webserver + daemon in compose) with software-defined assets backed by Iceberg/Trino and MLflow tracking.

## Alternatives considered

| Option | Why not primary |
|--------|-----------------|
| **Airflow** | Task/DAG-first; weaker asset lineage UX for lakehouse + ML feature tables |
| **Prefect** | Lighter; less lakehouse-native asset model for this design |
| **Cron + scripts** | No lineage, retries, or operator UI |

## Consequences

- Asset graph matches how we talk about the platform (“materialize quarantine audit”).
- Retrain is an event + MLflow run, not a hidden side effect inside a consumer.
- Local compose must keep Postgres for Dagster/MLflow storage.
