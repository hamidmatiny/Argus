# Multi-feature drift storm

## Symptoms

- Multiple features drift in one window (`multi_feature_drift` in incident reasons)
- Alertmanager fires fleet-level critical to incident-engine mock inbox
- Dashboard shows several open incidents close together

## Likely causes

1. Correlated sensor suite failure (lidar_temp + compute_load + sensor_status)
2. Bad deploy of ingestion normalizer rewriting fields
3. Clock jump / batch replay dumping stale distribution into validated topic

## Investigation steps

1. `search_similar_incidents` for prior multi-feature storms
2. List open incidents filtered by severity CRITICAL
3. Pull drift report feature list and compare to TelemetryEvent fields
4. Verify Redpanda / MSK consumer lag is not replaying old data

## Mitigation

- Treat as fleet-wide until proven otherwise
- Breakers may open for many vehicles — coordinate ack across operators
- Copilot may explain and cite runbooks; **must not** ack/resolve or retrain

## Citations

- Phase 4 + 7 escalation path
- Observability SLO alerts
