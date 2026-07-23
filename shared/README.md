# shared/

Single source of truth for every data shape that crosses an ARGUS service boundary.
Schemas here are versioned and regenerated into language-specific stubs; application
services must not invent parallel field names for the same concepts.

## Architecture

See topology / flow / ports sections below.

## Quick start

```bash
# From repo root
docker compose up -d --build
```

## Config

Primary knobs live in the root `.env.example` and the Configuration section below.

## Testing

See the Tests section below.

## What lives here

| Path | Role |
|------|------|
| `proto/` | Protobuf (`proto3`) IDL + Buf config (`buf.yaml`, `buf.gen.yaml`) |
| `gen/` | **Generated** Go and Python stubs from Buf (`make proto`) — do not hand-edit |
| `avro/` | Avro schemas for Kafka payloads + `register.sh` for Schema Registry |
| `contracts/v1/` | Pydantic v2 models + Pandera batch gates for in-Python validation |
| `contracts/CONTRACT_CHANGELOG.md` | Breaking-change policy and version history |
| `contracts/tests/` | Schema drift guardrails (`make contracts-test`) |

## Why three schema formats for one concept?

| Format | Used for | Why not only this? |
|--------|----------|--------------------|
| **Protobuf** | RPC / typed APIs between Go and Python services | Excellent for polyglot codegen; Kafka ecosystems usually prefer Avro + Schema Registry for topic evolution |
| **Avro** | Kafka message payloads + Confluent-compatible Schema Registry compatibility checks | First-class subject versioning and compatibility modes (BACKWARD/FORWARD/FULL); weaker as a general RPC IDL |
| **Pydantic / Pandera** | Fast in-process validation before anything hits Kafka (and batch DataFrame gates) | Python-native DX and rich validation; not a wire format for Go or registry-enforced topics |

Keep **field names** identical across all three for `TelemetryEvent` (and proto ↔ Pydantic for `IncidentEvent`). `make contracts-test` fails the build if they drift.

## Regenerating code after editing a `.proto`

```bash
# from repo root
make proto
# runs: buf lint + buf generate (writes shared/gen/{go,python})

make contracts-test
# runs pytest drift guardrails (requires proto gen + contracts deps)
```

Workflow:

1. Edit `shared/proto/argus/v1/*.proto` (additive changes preferred within a major).
2. Mirror field changes in `shared/avro/*.avsc` and `shared/contracts/vN/`.
3. Document breaking changes in `contracts/CONTRACT_CHANGELOG.md` and bump `vN` if needed.
4. `make proto && make contracts-test`
5. Optionally register Avro with the local registry (stack must be up):

```bash
make up
make register-avro
# Schema Registry: http://localhost:18081
# Redpanda Console: http://localhost:8087
```

## Local Schema Registry

Redpanda exposes a Confluent-compatible Schema Registry on host port **18081**.
`redpanda-console` is included in `docker-compose.yml` for browsing topics and subjects.

## Contract versioning

- Python contracts live under `shared/contracts/v1/` (future: `v2/`, …).
- **No breaking changes without a version bump** — see `CONTRACT_CHANGELOG.md`.