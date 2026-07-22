# drift-monitor

Statistical **data drift** detection for ARGUS — a port/upgrade of sentinel-ray’s
`DriftAnalyzer` that reads the clean `telemetry.validated` stream from Kafka
instead of an in-process Ray buffer.

## What it catches (vs Phase 3 QA)

| Layer | Catches | Misses |
|-------|---------|--------|
| **stream-processor (QA)** | Malformed / out-of-contract records (bad GPS, empty IDs, illegal enums) | Perfectly schema-valid data whose *distribution* has shifted |
| **drift-monitor (this)** | Valid-but-suspicious data — the model’s world has moved (sensor bias, fleet mix change, seasonal load) | Schema violations (already removed upstream) |

QA is a contract gate. Drift-monitor is a **distributional** gate: every record it
sees already passed Pandera-equivalent checks.

## Method

1. **Live golden baseline** — on startup, accumulate the first
   `DRIFT_BASELINE_SAMPLES` records from `telemetry.validated` and freeze that
   as the reference (`baseline_ready=true` only then). `/health` stays
   non-ready until the live baseline exists. A synthetic Gaussian from
   `GOLDEN_BASELINE` is an empty-topic fallback only
   (`DRIFT_USE_LIVE_BASELINE=false`); empiric mean/std approximate the simulator
   but are **not** a substitute for live traffic, and any synthetic seed is
   replaced the moment enough real samples arrive. Analysis waits for the live
   baseline so KS never runs against a mismatched fictional reference.
2. **Sliding-window KS test** — for each window of `DRIFT_WINDOW_SIZE` validated
   events, run a two-sample Kolmogorov-Smirnov test vs baseline (`DRIFT_ALPHA`,
   default `0.05`). Same core statistic as sentinel-ray. Incidents publish on
   rising-edge only so overlapping windows do not spam `incidents.raw`.
3. **Embedding distance** — the 4-D feature vector is treated as a tabular
   embedding (z-scored). Window vs baseline **centroid** cosine similarity and
   Euclidean distance are checked against
   `EMBEDDING_COSINE_SIM_THRESHOLD` / `EMBEDDING_EUCLIDEAN_THRESHOLD`, plus a KS
   on embedding L2 norms (sentinel-ray pattern).
4. **Evidently AI** — each evaluation window also runs `DataDriftPreset`; HTML
   lands in `DRIFT_REPORTS_DIR`, and per-feature scores feed Prometheus gauges.
5. **Incidents** — if `drifted_feature_count >= DRIFT_MIN_FEATURES_FOR_INCIDENT`
   (default `2`), publish a structured `IncidentEvent` (shared proto / JSON) to
   `incidents.raw` for incident-engine (Phase 7).

## Topics

```text
telemetry.validated ──► drift-monitor ──► incidents.raw
                              │
                              ├── Evidently HTML reports/
                              └── Prometheus /metrics
```

## Endpoints

| Path | Port (default) | Purpose |
|------|----------------|---------|
| `GET /health` | `8094` | Liveness + stats |
| `GET /metrics` | `8094` or `8095` | Prometheus: `argus_drift_feature_score`, baseline staleness, records evaluated, incidents |

## Configuration

| Env | Default | Meaning |
|-----|---------|---------|
| `DRIFT_SOURCE_TOPIC` | `telemetry.validated` | Input |
| `DRIFT_INCIDENTS_TOPIC` | `incidents.raw` | Output incidents |
| `DRIFT_BASELINE_SAMPLES` | `200` | Live reference window size |
| `DRIFT_BASELINE_WARMUP_SAMPLES` | `200` | Discarded before freezing baseline (avoid cold-start kinematics) |
| `DRIFT_WINDOW_SIZE` | `50` | Sliding analysis window |
| `DRIFT_ALPHA` | `0.05` | KS significance |
| `DRIFT_MIN_FEATURES_FOR_INCIDENT` | `2` | Incident threshold (sentinel-ray) |
| `DRIFT_USE_LIVE_BASELINE` | `true` | Accumulate live reference (default); `false` seeds synthetic cold-start only |
| `DRIFT_HEALTH_PORT` / `DRIFT_METRICS_PORT` | `8094` / `8095` | HTTP |

## Run

```bash
# tests
make drift-monitor-test

# compose (with validated traffic flowing)
make up
curl -s localhost:8094/health | jq .
curl -s localhost:8095/metrics | head
```

## Tests

- Unit: KS on synthetic drifted vs non-drifted arrays; embedding centroid shift;
  multi-feature incident threshold.
- Integration: end-to-end synthetic drift → `IncidentEvent` (in-memory always;
  Kafka when Redpanda is up).
