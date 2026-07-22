# stream-processor

Streaming **QA contract-enforcement gate** for ARGUS. Consumes normalized
fleet telemetry, validates each record against the shared Pandera-equivalent
rules, and routes to validated / quarantine topics with rolling quarantine-rate
metrics — a modernization of sentinel-ray’s `QAValidationWorker` and
hydra-data-factory’s Pydantic/Pandera triage, as a real streaming job.

## Division of responsibility

| Layer | Role |
|-------|------|
| **`ingestion/ray_consumer`** | Decode / type-coerce only. Must **not** clamp ranges or invent defaults. Structural failures → `telemetry.quarantine` with `source_topic=telemetry.raw`. |
| **`stream-processor` (this service)** | **Single authority** on semantic pass/fail. Range, enum, regex, and required-field checks live here — and only here. |

Ray publishes pass-through (possibly out-of-range) events to `telemetry.normalized`
so this gate — and later drift-monitor — see the real anomaly signal.

## Topic topology

```text
telemetry.raw
      │
      ├──► telemetry.quarantine     ← ray-consumer (structural; source_topic=telemetry.raw)
      ▼
telemetry.normalized            ← ray-consumer (pass-through)
      │
      ▼
 stream-processor (QA gate)     ← sole semantic authority
      │
      ├──► telemetry.validated     # contract-clean events (Avro)
      ├──► telemetry.quarantine    # semantic DLQ (source_topic=telemetry.normalized)
      └──► telemetry.qa_metrics    # per-vehicle tumbling quarantine rate (JSON)
```

| Topic | Content |
|-------|---------|
| `telemetry.normalized` | Pass-through from Ray (may still fail semantic checks) |
| `telemetry.validated` | Passes all contract checks |
| `telemetry.quarantine` | Shared DLQ (`field`, `rule`, `reason`, `violations`, `raw_payload`); use `source_topic` to tell ray vs QA |
| `telemetry.qa_metrics` | Windowed `{vehicle_id, quarantine_rate, exceeded, ...}` |

## Engines: `--engine=local|flink`

| Engine | When to use |
|--------|-------------|
| **`local`** (default in compose) | Pure-Python Kafka consumer/producer implementing the same validation + tumbling windows. No Flink cluster required — honest fallback for laptops/CI. |
| **`flink`** | PyFlink DataStream job with checkpointing and Kafka connectors. Submit against the compose JobManager/TaskManager (or any Flink cluster). |

```bash
# local engine
python stream-processor/main.py --engine local --broker localhost:19092

# Flink engine (requires apache-flink + connector jar)
pip install apache-flink==1.18.1
python stream-processor/main.py --engine flink --broker redpanda:9092
```

Shared core: `validation/rules.py` + `validation/metrics.py` — both engines call
the same functions (Flink via `map_validation` / `QuarantineRateAggregator`).

## Why Flink?

Not “because streaming is cool” — concrete reasons for this gate:

1. **Exactly-once processing semantics** — checkpointed Kafka sinks so a QA
   restart does not double-emit validated / quarantine records.
2. **Windowed aggregation** — native keyed tumbling windows for per-vehicle
   quarantine rates (the sentinel-ray `ORCHESTRATOR_QA_WINDOW_*` pattern),
   without hand-rolled timers in every consumer.
3. **Backpressure handling** — Flink’s network stack slows sources when sinks
   or validators lag, protecting Redpanda and downstream lakehouse writers
   under bursty fleet load.
4. **Operational scale-out** — raise TaskManager parallelism without rewriting
   the consumer loop; the local engine remains the portable logic check.

## Quarantine-rate window

Mirrors sentinel-ray defaults:

| Env | Default | Meaning |
|-----|---------|---------|
| `QA_WINDOW_EVENTS` | `20` | Tumbling event count per vehicle |
| `QA_QUARANTINE_RATE_THRESHOLD` | `0.15` | `exceeded=true` when rate > threshold |

## Configuration

| Env / flag | Default |
|------------|---------|
| `QA_ENGINE` / `--engine` | `local` |
| `KAFKA_BROKERS` / `--broker` | `localhost:19092` |
| `QA_SOURCE_TOPIC` | `telemetry.normalized` |
| `QA_VALIDATED_TOPIC` | `telemetry.validated` |
| `QA_QUARANTINE_TOPIC` | `telemetry.quarantine` |
| `QA_METRICS_TOPIC` | `telemetry.qa_metrics` |
| `QA_HEALTH_PORT` | `8093` (`GET /health`) |

## Docker compose

```bash
make up
# Flink UI: http://localhost:8088
# QA health: http://localhost:8093/health
```

Services:

- `flink-jobmanager` / `flink-taskmanager` — Flink 1.18 cluster wired to the
  compose network (reachable to Redpanda as `redpanda:9092`)
- `stream-processor` — runs `--engine=local` by default so the QA path is
  reliable without PyFlink jars; set `QA_ENGINE=flink` to submit the PyFlink job

## Tests

```bash
make stream-processor-test
```

- Unit tests: validation rules + both engines’ map/aggregate helpers (no cluster)
- Integration: produces known-good / known-bad events to Kafka and asserts
  routing (skipped automatically if Redpanda is down)
