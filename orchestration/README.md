# orchestration

**Dagster** software-defined assets that close the ARGUS MLOps loop: Iceberg
feature stats → Evidently drift decisions → **MLflow** lineage + Kafka
`orchestration.retraining_triggered`. This replaces sentinel-ray’s ad-hoc
“queue a retraining webhook” with a real orchestrator and observable asset graph.

Optional **Feast** definitions live under [`feature_store/`](./feature_store/)
(advanced module — see that README).

## Asset graph

```text
fleet.telemetry (Iceberg)
        │
        ▼
┌───────────────────────────┐
│ daily_feature_statistics  │  cron 06:00 UTC
│  mean/std/p50/p95         │──────► Feast offline parquet
│  per device_type          │
└───────────────────────────┘

drift-monitor Evidently JSON sidecars
        │
        ▼
┌───────────────────────────┐     drift_retrain_job
│ retrain_decision          │────────┬──────────────► trigger_retraining op
│  score / feature gates    │        │                      │
└───────────────────────────┘        │              ┌───────┴────────┐
                                     │              ▼                ▼
                                     │           MLflow run    Kafka topic
                                     │         (params+metrics)  orchestration.
                                     │                         retraining_triggered

fleet.quarantine (Iceberg)
        │
        ▼
┌───────────────────────────┐
│ weekly_quarantine_audit   │  cron Monday 07:00 UTC
│  top reasons / vehicles   │──► artifacts/weekly_quarantine_audit.json
└───────────────────────────┘
```

## Retraining lineage (vs sentinel-ray)

| sentinel-ray | ARGUS orchestration |
|--------------|---------------------|
| Async HTTP POST to `RETRAINING_WEBHOOK_URL` | Structured Kafka event on `orchestration.retraining_triggered` |
| Local JSON fallback when webhook down | MLflow run always logged with drift scores / window / reason |
| No experiment tracking | MLflow UI (`:5002`) for params + metrics |

Flow: **drift-monitor** writes `reports/latest_drift_signal.json` → Dagster
`retrain_decision` / `drift_retrain_job` → **MLflow** + **Kafka**.

## Local services

| Service | Port | URL |
|---------|------|-----|
| Dagster webserver | **3000** | http://localhost:3000 — asset graph UI |
| MLflow tracking | **5002** → container `5000` | http://localhost:5002 |
| Postgres (MLflow backend) | **5433** | `argus` / `argus` / db `mlops` |

```bash
make up
# open Dagster UI
open http://localhost:3000

# materialize feature stats (uses Iceberg when stack is up)
docker compose exec dagster-webserver \
  dagster asset materialize -m argus_orchestration.definitions \
  --select 'lakehouse/daily_feature_statistics'

# run drift → retrain job
docker compose exec dagster-webserver \
  dagster job execute -m argus_orchestration.definitions -j drift_retrain_job
```

## Configuration

| Env | Default | Meaning |
|-----|---------|---------|
| `MLFLOW_TRACKING_URI` | `http://localhost:5001` | Tracking server |
| `MLFLOW_EXPERIMENT_NAME` | `argus-retraining` | Experiment |
| `DRIFT_REPORTS_DIR` | `../drift-monitor/reports` | Evidently sidecars |
| `ORCH_RETRAIN_MAX_SCORE_THRESHOLD` | `0.5` | Max feature score gate |
| `ORCH_RETRAIN_MIN_DRIFTED_FEATURES` | `2` | Count gate (matches drift-monitor) |
| `ORCH_RETRAINING_TOPIC` | `orchestration.retraining_triggered` | Kafka lineage topic |

## Tests

```bash
make orchestration-test
```

Uses `dagster.materialize` against Parquet fixtures (no live Iceberg/Kafka required).

## Feast (optional)

See [`feature_store/README.md`](./feature_store/README.md). After materializing
`daily_feature_statistics`, run `feast apply` in that directory.
