# Serverless ETL demo module

**What this is:** an AWS-native orchestration skill demo (Lambda container image × 4 entrypoints, Step Functions, optional EventBridge, SQS DLQ) patterned after [hydra-data-factory](https://github.com/hamidmatiny/hydra-data-factory)’s Phase 9 design.

**What this is not:** the production ARGUS data path. Real-time telemetry still flows Kafka/MSK → Ray → stream-processor → **Iceberg `fleet.telemetry`** (Dagster/MLflow on top). This module never writes the Iceberg warehouse prefix and never owns `fleet.telemetry`.

## Layout

| Path | Role |
|------|------|
| `serverless/raw/{execution_id}/batch.json` | Generated batch |
| `serverless/staging/{execution_id}/validated.parquet` | Pandera-passed rows |
| `serverless/dead_letter/{execution_id}/rejected.json` | Rejected records |
| `serverless/telemetry/dt=<date>/{execution_id}.parquet` | Final Parquet |
| `serverless/dead_letter/failures/{execution_id}.json` | Pipeline failure metadata |
| Glue `fleet.serverless_batches` | Partition catalog for the demo table only |

Validation reuses `shared/contracts/v1/pandera_schemas.py::validate_telemetry_batch`. Generation reuses `ingestion/simulator/generator.py::VehicleTelemetrySimulator`.

## Cost controls

- `enable_eventbridge_schedule` defaults to **`false`** — apply does not start a daily cron.
- ECR `force_delete = true` so teardown is not blocked by leftover images.

## Build & push the Lambda image

```bash
# after terraform apply (or plan) to learn the repository URL
REPO=$(terraform -chdir=infra/terraform/environments/dev output -raw serverless_etl_ecr_repository_url)

aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin "${REPO%%/*}"
docker build -f infra/terraform/modules/serverless-etl/lambda/Dockerfile \
  -t "${REPO}:latest" .
docker push "${REPO}:latest"
```

Then start an execution manually, or set `enable_eventbridge_schedule = true` when you intend the daily trigger.

## IAM

Separate roles for Lambda (S3 `serverless/*` only + Glue table-scoped + SQS send + logs), Step Functions (invoke the four functions + logging), and EventBridge (start execution, only when the schedule is enabled).
