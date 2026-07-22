# ingestion/

Fleet telemetry **entry point** for ARGUS: a configurable simulator publishes
Avro `TelemetryEvent` messages to Kafka, and a Ray Core consumer pool normalizes
them onto a downstream topic.

## Message flow

```text
simulator  --Avro(Confluent)-->  telemetry.raw
                                      │
                          Ray DataStreamer actor pool
                          (normalize / quarantine)
                                      │
                                      ▼
                               telemetry.normalized
```

| Topic | Producer | Consumer | Payload |
|-------|----------|----------|---------|
| `telemetry.raw` | `ingestion/simulator` | `ingestion/ray_consumer` | Confluent-wire Avro `TelemetryEvent` (plus occasional corrupt JSON bytes) |
| `telemetry.normalized` | `ingestion/ray_consumer` | Flink QA (later) | Clean / repaired Avro `TelemetryEvent` |

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
concurrent `process_batch` via `ray.get`.

| Flag / env | Default | Meaning |
|------------|---------|---------|
| `KAFKA_BROKERS` | `localhost:19092` | Brokers |
| `INGESTION_RAW_TOPIC` | `telemetry.raw` | Source |
| `INGESTION_NORMALIZED_TOPIC` | `telemetry.normalized` | Destination |
| `INGESTION_KAFKA_GROUP_ID` | `argus-ingestion` | Consumer group prefix |
| `RAY_NUM_PARTITIONS` | `4` | Actor pool size |
| `RAY_NUM_CPUS` | `2` | Local Ray CPUs |
| `RAY_HEALTH_PORT` | `8092` | `GET /health` |
| `RAY_DASHBOARD_PORT` | `8265` | Ray dashboard |

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

## Tests

```bash
make ingestion-test
# or:
cd ingestion && ../ingestion/.venv/bin/pytest -q
```

Uses a tiny local Ray process (`num_cpus=2`, no dashboard) for CI-speed actor
fan-out checks — not an external cluster.
