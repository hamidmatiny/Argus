# ingestion

**What it does:** Fleet simulator publishes Avro to `telemetry.raw`; Ray `DataStreamer` actors normalize to `telemetry.normalized`.

**Ports:** simulator `:8091` · ray-consumer `:8092`

Canonical detail: [`ingestion/README.md`](https://github.com/hamidmatiny/Argus/blob/main/ingestion/README.md)
