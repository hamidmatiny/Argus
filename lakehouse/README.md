# lakehouse

Durable, queryable storage for ARGUS Phase-3 streams using **Apache Iceberg** —
an ACID open table format with schema evolution, time travel, and multi-engine
reads. This is a deliberate upgrade from hydra-data-factory’s Hive-partitioned
Parquet layout (same Snappy Parquet files underneath, transactional metadata
on top).

## Architecture

```text
telemetry.validated ──► lakehouse-writer ──► Iceberg fleet.telemetry
                                                  │
telemetry.quarantine ─► lakehouse-dlq-writer ──► Iceberg fleet.quarantine
                                                  │
                              MinIO (s3://warehouse) + Iceberg REST catalog
                                                  │
                                               Trino SQL
```

| Table | Topic | Why |
|-------|-------|-----|
| `fleet.telemetry` | `telemetry.validated` | Clean, contract-passed fleet events |
| `fleet.quarantine` | `telemetry.quarantine` | Audit archive — nothing silently dropped |

## Why Iceberg over raw Hive-partitioned Parquet

| Capability | Hive / directory Parquet (hydra) | Apache Iceberg (ARGUS) |
|------------|----------------------------------|-------------------------|
| **ACID commits** | Directory listing; partial writes visible | Snapshot isolation; readers see committed data only |
| **Schema evolution** | Manual / brittle partition discovery | First-class add/rename/widen with metadata |
| **Time travel** | Object-version hope | `FOR VERSION AS OF` / snapshot IDs |
| **Concurrent writers** | Easy to corrupt `_SUCCESS` layouts | Optimistic concurrency on metadata |
| **Compaction** | DIY Spark jobs on file soup | Rewrite manifests / data files against snapshots |
| **Multi-engine** | Engine-specific metastore quirks | Same table via REST / Glue for Trino, Spark, PyIceberg |
| **Partition evolution** | Painful directory renames | Evolve specs without rewriting history |

Local warehouse is **MinIO**; production uses real S3 with **AWS Glue** as the
catalog (hydra continuity — see [`catalog/README.md`](./catalog/README.md)).

## Partitioning

`fleet.telemetry` is partitioned by:

1. **`device_type`** (identity) — continuity with hydra’s Glue `device_type`
   partition; isolates simulator vs vehicle traffic for cheap scans.
2. **`day(timestamp)`** (`event_day`) — time-bounded analytics and retention.

`fleet.quarantine` uses **`day(rejected_at)`** for audit windows.

Data files remain **Snappy-compressed Parquet** (`write.parquet.compression-codec=snappy`).

## Query examples (Trino)

```bash
# CLI against local Trino (host UI/API: localhost:8089)
docker compose exec trino trino --execute "SHOW TABLES FROM iceberg.fleet"
docker compose exec trino trino --execute "SELECT * FROM iceberg.fleet.telemetry LIMIT 10"
```

```sql
-- Recent simulator traffic
SELECT vehicle_id, speed_mph, device_type, timestamp
FROM iceberg.fleet.telemetry
WHERE device_type = 'DEVICE_TYPE_SIMULATOR'
ORDER BY timestamp DESC
LIMIT 10;

-- Partition prune by day
SELECT count(*) AS events
FROM iceberg.fleet.telemetry
WHERE event_day = DATE '2026-07-22';

-- Quarantine audit (nothing silently dropped)
SELECT rejected_at, vehicle_id, field, rule, reason
FROM iceberg.fleet.quarantine
ORDER BY rejected_at DESC
LIMIT 20;

-- Time travel (after writers have produced multiple snapshots)
SELECT * FROM iceberg.fleet.telemetry FOR VERSION AS OF 1 LIMIT 5;
```

## Endpoints & ports

| Service | Port | Purpose |
|---------|------|---------|
| MinIO API | `9000` | S3 warehouse |
| MinIO console | `9001` | Browser UI (`admin` / `password`) |
| Iceberg REST | `8181` | Catalog API |
| Trino | `8089` → container `8080` | SQL |
| lakehouse-writer `/health` | `8096` | Validated → telemetry |
| lakehouse-dlq-writer `/health` | `8097` | Quarantine → quarantine |

## Configuration

| Env | Default | Meaning |
|-----|---------|---------|
| `ICEBERG_CATALOG_TYPE` | `rest` | `rest` local / `glue` prod |
| `ICEBERG_CATALOG_URI` | `http://localhost:8181` | REST catalog |
| `ICEBERG_WAREHOUSE` | `s3://warehouse/` | Object store root |
| `S3_ENDPOINT` | `http://localhost:9000` | MinIO or AWS |
| `LAKEHOUSE_BATCH_SIZE` | `50` | Rows per Iceberg append |
| `LAKEHOUSE_FLUSH_INTERVAL_SEC` | `5` | Max buffer latency |

## Run

```bash
make up
make lakehouse-test

curl -s localhost:8096/health | jq .
curl -s localhost:8097/health | jq .

docker compose exec trino trino --execute \
  "SELECT count(*) FROM iceberg.fleet.telemetry"
```

## Tests

Pytest uses a **SqlCatalog + local `file://` warehouse** fixture (no MinIO
required) to exercise schema mapping, partition specs, and appends.
