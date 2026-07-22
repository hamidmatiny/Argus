# Contract changelog — ARGUS shared Python contracts

## Policy: no breaking changes without a version bump

Contracts under `shared/contracts/vN/` are **semantically versioned by directory**.

| Change type | Allowed in-place on `vN`? | Required action |
|-------------|---------------------------|-----------------|
| Add optional field with default | Yes (additive) | Document here; regenerate Avro/proto if wire formats change |
| Tighten validation (narrower regex/range) | **No** (breaking for producers) | Bump to `vN+1`, keep `vN` until consumers migrate |
| Rename / remove field | **No** | New major `vN+1` |
| Change field type | **No** | New major `vN+1` |
| Loosen validation | Yes (usually) | Document; confirm downstream still safe |

Wire formats (`shared/proto`, `shared/avro`) must stay field-name aligned with the active contract version. The `make contracts-test` suite is the drift guardrail.

---

## v1 — 2026-07-22

Initial contract surface:

- **TelemetryEvent** — fleet sample fields (vehicle/trip IDs, GPS, speed, brake, lidar temp, compute load, sensor status, hardware version, device type)
- **IncidentEvent** — incident_id, severity, source_service, metric_name, threshold, observed_value, timestamp, status
- **Pandera gate** — batch validation: `speed_mph` ∈ [0, 120], `gps_lat` ∈ [-90, 90], `gps_lon` ∈ [-180, 180], `vehicle_id` regex `^VH-[0-9]{4,8}$`, required `timestamp`
