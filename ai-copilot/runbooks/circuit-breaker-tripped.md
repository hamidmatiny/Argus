# Circuit breaker tripped for a vehicle

## Symptoms

- Incident severity `CRITICAL` with reason containing `breaker` or `circuit_open`
- `GET /breakers` on incident-engine shows the vehicle in `open` or `half_open`
- Dashboard Overview "Open breakers" gauge > 0
- Operator chat: "why did vehicle VH-XXXX trip its breaker?"

## Likely causes

1. **Repeated QA / sensor faults** on that vehicle (lidar_temp, compute_load, sensor_status FAULT)
2. **Drift-driven escalation** that opened the breaker via OPA policy
3. **Half-open probe failure** re-tripping after a recovery attempt

## Investigation steps

1. `argusctl incidents list --status open` — confirm the escalated incident id
2. Query telemetry for the vehicle around the trip time via gateway:
   `SELECT * FROM telemetry WHERE vehicle_id = 'VH-XXXX' AND ts > …`
3. Check stream-processor QA quarantine rate for that vehicle
4. Inspect incident-engine breaker state: `GET http://localhost:8098/breakers`

## Mitigation

- Acknowledge the incident in the dashboard (operator role) once a human owns it
- If telemetry shows a bad sensor, quarantine the vehicle in ops runbooks (manual)
- Do **not** auto-resolve; wait for HalfOpen success or explicit resolve after root cause

## Citations

- Phase 7 incident-engine circuit breaker docs
- OPA policies under `incident-engine/policies/`
