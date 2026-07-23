# ingestion/

Fleet telemetry **entry point** for ARGUS: a configurable simulator publishes
Avro `TelemetryEvent` messages to Kafka, and a Ray Core consumer pool
**pass-through normalizes** them onto a downstream topic.

## Config

Primary knobs live in the root `.env.example` and the Configuration section below.

## Division of responsibility

| Layer | Role |
|-------|------|
| **`ray_consumer`** | Decode + unambiguous type coercion only (e.g. numeric string → float, timestamp → ISO-8601). **No** range clamping, **no** enum/default substitution. Structural failures → `telemetry.quarantine`. |
| **`stream-processor`** | **Single authority** on semantic pass/fail (Pandera-equivalent ranges, enums, vehicle_id regex). Writes `telemetry.validated` / `telemetry.quarantine` / `telemetry.qa_metrics`. |

Do not reintroduce clamping or silent defaults in `normalize_record` — that starves
QA and drift-monitor of real anomaly signal.

## Message flow

```text
simulator  --Avro(Confluent)-->  telemetry.raw
                                      │
                          Ray DataStreamer actor pool
                          (decode / coerce only)
                           │                    │
                           ▼                    ▼
                 telemetry.normalized    telemetry.quarantine
                 (pass-through)          (structural only;
                                          source_topic=telemetry.raw)
                           │
                           ▼
                    stream-processor QA
```

| Topic | Producer | Consumer | Payload |
|-------|----------|----------|---------|
| `telemetry.raw` | `ingestion/simulator` | `ingestion/ray_consumer` | Confluent-wire Avro `TelemetryEvent` (plus occasional corrupt JSON bytes) |
| `telemetry.normalized` | `ingestion/ray_consumer` | `stream-processor` | Pass-through Avro (may still be semantically invalid) |
| `telemetry.quarantine` | `ray_consumer` + `stream-processor` | ops / lakehouse | Shared DLQ schema; distinguish via `source_topic` |

## Components

### `simulator/`

Port of hydra-data-factory kinematics + vanguard anomaly injection.

| Flag | Env | Default | Meaning |
|------|-----|---------|---------|
| `--vehicles` | `SIMULATOR_VEHICLES` | `5` | Simulated fleet size (`VH-0000001`…) |
| `--rate` | `SIMULATOR_RATE` | `10` | Aggregate events/sec |
| `--duration` | `SIMULATOR_DURATION` | `0` | Seconds (`0` = forever) |
| `--failure-rate` | `SIMULATOR_FAILURE_RATE` | `0.05` | Corruption / anomaly probability |
| `--topic` | `SIMULATOR_TOPIC` | `telemetry.raw` | Kafka topic |
| `--broker` | `KAFKA_BROKERS` | `localhost:19092` | Bootstrap brokers |
| `--schema-registry` | `SCHEMA_REGISTRY_URL` | `http://localhost:18081` | Schema Registry |
| `--health-port` | `SIMULATOR_HEALTH_PORT` | `8091` | `GET /health` |

Corruption strategies: `drop_vehicle_id`, `invalid_speed`, `malformed_gps`,
`null_timestamp`, `missing_fields`, `corrupt_json`. Runtime anomalies:
`cpu_spike`, `memory_leak`.

### `ray_consumer/`

Sentinel-ray-style **DataStreamer** actor pool: one actor per partition,
concurrent `process_batch` via `ray.get`. Pass-through only — see above.

Structural drops (empty `vehicle_id`, unparseable timestamp, non-numeric GPS/speed,
undecodable payload) are published to `telemetry.quarantine` with the same JSON
schema as stream-processor (`field`, `rule`, `reason`, `violations`, `raw_payload`,
`source_topic=telemetry.raw`).

| Flag / env | Default | Meaning |
|------------|---------|---------|
| `KAFKA_BROKERS` | `localhost:19092` | Brokers |
| `INGESTION_RAW_TOPIC` | `telemetry.raw` | Source |
| `INGESTION_NORMALIZED_TOPIC` | `telemetry.normalized` | Pass-through destination |
| `INGESTION_QUARANTINE_TOPIC` | `telemetry.quarantine` | Structural DLQ |
| `INGESTION_KAFKA_GROUP_ID` | `argus-ingestion` | Consumer group prefix |
| `RAY_NUM_PARTITIONS` | `2` | Actor pool size (keep ≤ CPUs under 2Gi) |
| `RAY_NUM_CPUS` | `2` | Local Ray CPUs |
| `RAY_OBJECT_STORE_MEMORY_BYTES` | `268435456` (256MB) | Explicit object-store size for `ray.init` |
| `RAY_MEMORY_BYTES` | `536870912` (512MB) | Explicit task/actor heap (`_memory`) |
| `RAY_INCLUDE_DASHBOARD` | `false` | Enable Ray UI (needs more than 2Gi) |
| `RAY_HEALTH_PORT` | `8092` | `GET /health` |
| `RAY_DASHBOARD_PORT` | `8265` | Ray dashboard (only if enabled) |

## Run standalone

```bash
# from repo root — Redpanda must be up
make up
make register-avro

python -m venv ingestion/.venv
source ingestion/.venv/bin/activate
pip install -r ingestion/requirements.txt
export PYTHONPATH=.
export ARGUS_AVRO_SCHEMA_PATH=shared/avro/telemetry_event.avsc

# terminal 1
python -m ingestion.simulator --vehicles 5 --rate 20 --failure-rate 0.1 \
  --broker localhost:19092 --topic telemetry.raw

# terminal 2
python -m ingestion.ray_consumer --broker localhost:19092 \
  --source-topic telemetry.raw --dest-topic telemetry.normalized
```

Health: http://localhost:8091/health · http://localhost:8092/health · Ray UI http://localhost:8265

## Run via compose

```bash
make up   # builds simulator + ray-consumer with 2 CPU / 2Gi limits
make logs
```

## Running in Docker / troubleshooting

Ray inside a **cgroup memory-limited** container (our compose limit is 2Gi) often
fails at startup with:

```text
ValueError: ... memory on this node available for tasks and actors (0.0 GB) is less than 0%
```

**Cause:** `ray.init()` auto-detects available memory from the host/cgroup view and
can resolve it to `0` under Docker limits. Raising the container limit alone masks
this on larger machines; it is not the real fix.

**Fix (already applied in this service):**

1. Pass explicit budgets via env (wired into `initialize_ray` → `ray.init`):
   - `RAY_OBJECT_STORE_MEMORY_BYTES` (default `268435456` / 256MB)
   - `RAY_MEMORY_BYTES` (default `536870912` / 512MB) → `ray.init(_memory=...)`
2. Set `shm_size: "1gb"` on the `ray-consumer` service — the object store is backed
   by `/dev/shm`, and Docker’s default 64MB shm is a common companion failure mode.
3. Keep `RAY_INCLUDE_DASHBOARD=false` under the 2Gi limit — the dashboard’s
   multi-process UI can consume ~1GB+ by itself and trigger Ray’s OOM killer
   even after (1)+(2). Enable only if you raise the container memory.
4. Default `RAY_NUM_PARTITIONS=2` so actor workers fit beside Ray’s GCS/raylet.

Tune the memory env vars if you change the container limit; keep
`object_store + _memory` comfortably under the cgroup cap (leave headroom for the
Python process, Kafka clients, and Ray system daemons). Do **not** treat a higher
memory limit as a substitute for explicit `object_store_memory` / `_memory`.

Progress is logged every ~10s as `ray_consumer_progress` with cumulative
`consumed` / `published` / `quarantined` counts.

## Tests

```bash
make ingestion-test
# or:
cd ingestion && ../ingestion/.venv/bin/pytest -q
```

Uses a tiny local Ray process (`num_cpus=2`, no dashboard) for CI-speed actor
fan-out checks — not an external cluster.