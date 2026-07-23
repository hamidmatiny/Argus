# simulation — scenario-based synthetic sensor pipeline

Sources → Transforms → Sinks framework (`argus_pipeline`) that turns scripted driving
scenarios into synchronized synthetic camera/lidar frames and writes them to Iceberg
tables **alongside** (not instead of) real fleet telemetry.

## What this is / isn't

| | |
|--|--|
| **Is** | A laptop-budget scenario generator for targeted synthetic training data; classical sensor proxies; Iceberg sinks via existing `lakehouse/` writers |
| **Is not** | A replacement for Kafka/Ray/Iceberg `fleet.telemetry`; not a real NeRF / Gaussian-splatting neural renderer |

`camera_rendering` and `lidar_rendering` expose a **neural-renderer-shaped interface**
(pose → modality payload + intrinsics/extrinsics) but the backend is explicitly
`classical_proxy`. Real neural rendering is out of scope for local/dev budgets —
documented here so we do not overclaim.

## Framework

```text
scenario_runner  →  physics  →  camera_rendering ─┐
                        └────→  lidar_rendering ──┼→ fuse_frame_transforms → transform_interface
                                                  └→ fuse_rendered_data → synthetic_sensor_data
                         physics ──────────────────→ scenario_ground_truth
```

- **Sources** (`argus_pipeline.sources`): `scenario_runner` — intersection / highway_merge /
  pedestrian_crossing / hard_brake, extending `VehicleTelemetrySimulator` kinematics.
- **Transforms** (`argus_pipeline.transforms`): `physics`, `camera_rendering`,
  `lidar_rendering`, `fuse_frame_transforms`, `fuse_rendered_data`.
- **Sinks** (`argus_pipeline.sinks`): Iceberg `fleet.scenario_ground_truth`,
  `fleet.synthetic_sensor_data`, `fleet.sensor_calibration` (transform_interface),
  using `lakehouse/common/{catalog,schema,sink}.py`.

Nodes register into a DAG via `@register` + `compose_dag` / `run_pipeline`.

## Drift → synthetic seed (Dagster)

`orchestration` graph `drift_to_retrain_graph` optionally runs
`seed_synthetic_scenarios_from_incident` **before** `trigger_retraining`:

- Maps Evidently feature scores (`brake_pressure`, `speed_mph`, …) → scenario params
- Produces a short synthetic run for the drifted signature
- Gated by `ORCH_SEED_SYNTHETIC_FROM_DRIFT` (default `true`); no-ops when
  `should_retrain=false` or the flag is off — never blocks retraining itself

## Run

```bash
make simulation-test

# Ad-hoc dry pipeline (in-process)
cd simulation && PYTHONPATH=.:.. \
  python -c "from argus_pipeline.runner import run_pipeline; print(run_pipeline({'n_frames': 4, 'dry_run': True, 'scenario_type': 'hard_brake'})['batch_sizes'])"
```

## Complements real telemetry

Real vehicles still stream into Kafka → Ray → Iceberg `fleet.telemetry`. This package
adds **scenario-conditioned synthetic sensors** for MLOps (edge-case replay after drift),
written to separate tables so production writers are never co-owned.
