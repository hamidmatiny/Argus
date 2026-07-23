# feature_store (optional / advanced)

**Feast** feature-store definition over the Dagster `daily_feature_statistics`
asset. This module is **optional** for the core ARGUS loop — the platform runs
without materializing online features — but a working local Feast repo is a
strong MLOps resume signal.

## What it provides

| Piece | Role |
|-------|------|
| Entity `device_type` | Join key for per-device aggregates |
| Feature view `device_feature_stats` | mean/std/p50/p95 for speed, brake, lidar, compute |
| Offline source | Parquet written by Dagster → `data/device_feature_stats.parquet` |
| Online store | Local SQLite (`data/online_store.db`) |

## Prereqs

1. Materialize the Dagster asset `lakehouse/daily_feature_statistics` (writes the Parquet).
2. From this directory:

```bash
cd orchestration/feature_store
feast apply
feast materialize-incremental $(date -u +%Y-%m-%dT%H:%M:%S)
feast get-online-features \
  --features device_feature_stats:speed_mph_mean \
  --entities device_type=DEVICE_TYPE_SIMULATOR
```

## Why optional

Feast adds offline→online sync and training/serving skew controls. ARGUS’s
critical path is Iceberg → Dagster → MLflow/Kafka; Feast sits beside that path
for feature serving demos and future model training jobs.
