# ingestion

High-throughput fleet telemetry ingestion layer built on **Ray**. Consumes device events from Kafka/Redpanda, normalizes payloads, and fans out to downstream QA and lakehouse pipelines.

**Status:** Scaffold only — implemented in a later phase.

**Language:** Python (Ray)

**Responsibilities (planned):**
- Kafka consumer groups for device / sensor / edge topics
- Schema validation and payload normalization
- Parallel batching and backpressure-aware writes toward Flink / Iceberg
