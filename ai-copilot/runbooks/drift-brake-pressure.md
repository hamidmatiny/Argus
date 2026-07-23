# Drift detected on brake_pressure

## Symptoms

- Drift-monitor publishes an incident with `metric_name` / feature `brake_pressure`
- Evidently report under `drift-monitor/reports/` shows DataDriftPreset hit on `brake_pressure`
- On-call / Alertmanager warning for drift score SLO

## Likely causes

1. **Simulator failure injection** raising brake_pressure distribution shift
2. **Fleet subset** (one hardware_version) reporting differently after a firmware bump
3. **Baseline staleness** — reference window no longer matches current traffic

## Investigation steps

1. Ask copilot / check `query_drift_report` for latest feature scores
2. Compare KS statistic for `brake_pressure` vs threshold in drift-monitor config
3. Sample recent validated telemetry: speed_mph vs brake_pressure correlation
4. Open the latest Evidently HTML report from the drift-reports volume

## Mitigation

- Confirm whether the shift is real fleet behavior vs bad sensors
- If real and model-impacting, operator may trigger retrain via gateway
  (`POST /v1/retraining:trigger`) — **humans only**, not the copilot
- Refresh baseline only after sign-off from data science

## Citations

- Phase 4 drift-monitor README
- Shared TelemetryEvent contract (`brake_pressure >= 0`)
