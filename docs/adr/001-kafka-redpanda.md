# ADR 001 — Kafka API via Redpanda (local) / MSK (prod)

**Status:** Accepted  
**Date:** 2026-07  
**Phases:** 0–2 (bus), 12 (MSK)

## Context

Fleet telemetry needs a durable, ordered, multi-consumer bus. Options: Apache Kafka, Redpanda, Pulsar, NATS JetStream, or cloud-only buses (Kinesis, Pub/Sub).

## Decision

- **Local:** Redpanda (Kafka API compatible) in docker compose — single binary, no ZooKeeper, fast cold start.
- **Production:** Amazon MSK (Kafka API) via Terraform — same producer/consumer code paths.

## Alternatives considered

| Option | Why not |
|--------|---------|
| Full Apache Kafka local | Heavier ops (ZK/KRaft), slower laptop UX |
| Pulsar | Strong multi-tenancy; steeper local ops for this portfolio |
| NATS JetStream | Excellent for light events; weaker fit for large fan-in telemetry archives + Kafka ecosystem sinks |
| Kinesis-only | Cloud lock-in; diverges local vs prod contracts |

## Consequences

- One Avro/Protobuf contract path works in both environments.
- Operators learn Kafka tooling (Console, consumer groups) that transfers to MSK.
- Must document advertised listeners carefully (`localhost:19092` vs `redpanda:9092`).
