# Iceberg catalog

ARGUS uses the **Iceberg REST catalog** locally (docker-compose) and **AWS Glue**
in production — the same Glue continuity hydra-data-factory used for Hive /
Parquet, upgraded to Iceberg table metadata.

## Local (REST + MinIO)

| Component | Role |
|-----------|------|
| `iceberg-rest` | REST catalog API (`ICEBERG_CATALOG_URI`) |
| `minio` | S3-compatible warehouse (`s3://warehouse/`) |
| Writers | PyIceberg `type=rest` + explicit `s3.endpoint` |

```bash
# From host (after make up)
export ICEBERG_CATALOG_URI=http://localhost:8181
export S3_ENDPOINT=http://localhost:9000
export AWS_ACCESS_KEY_ID=admin
export AWS_SECRET_ACCESS_KEY=password
```

## Production (Glue)

Set:

```bash
ICEBERG_CATALOG_TYPE=glue
GLUE_DATABASE=fleet          # or your Glue DB
GLUE_REGION=us-east-1
ICEBERG_WAREHOUSE=s3://your-argus-lakehouse/
AWS_ACCESS_KEY_ID=...
AWS_SECRET_ACCESS_KEY=...
```

PyIceberg loads the Glue catalog; tables remain queryable from Trino / Athena /
Spark with the Iceberg Glue catalog integration.

## Tables

| Table | Source topic | Partitioning |
|-------|--------------|--------------|
| `fleet.telemetry` | `telemetry.validated` | `device_type` + `day(timestamp)` |
| `fleet.quarantine` | `telemetry.quarantine` | `day(rejected_at)` |
