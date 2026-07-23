# simulation

**What it does:** Scenario-based synthetic sensor pipeline (Sources → Transforms → Sinks) that extends the fleet kinematic simulator into classical camera/lidar proxies and Iceberg tables `fleet.scenario_ground_truth` / `fleet.synthetic_sensor_data` — complementary to real telemetry, not a replacement. Optional Dagster seed from drift signatures ahead of retraining.

Canonical detail: [`simulation/README.md`](https://github.com/hamidmatiny/Argus/blob/main/simulation/README.md)
