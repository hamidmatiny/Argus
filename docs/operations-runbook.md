# Operations Runbook

Human-facing consolidation of the runbooks indexed by **ai-copilot** (`ai-copilot/runbooks/`). Use this during demos and on-call; the copilot may cite the same content but **cannot** mutate incidents.

## Golden signals (local)

| Check | Command / URL |
|-------|----------------|
| Gateway | `curl -sf http://localhost:8099/health` |
| QA | `curl -sf http://localhost:8093/health` |
| Drift | `curl -sf http://localhost:8094/health` |
| Incidents API | `curl -s http://localhost:8099/v1/incidents -H 'X-API-Key: demo-viewer'` |
| Grafana | http://localhost:3001 |
| Dashboard | http://localhost:3002 |
| Breakers | `curl -s http://localhost:8098/breakers` |

---

## 1. Quarantine rate spike

**Symptoms:** QA pass ratio SLO drops; `fleet.quarantine` grows; elevated `qa_reject` reasons.

**Likely causes:** High `SIMULATOR_FAILURE_RATE`; schema/contract drift; invalid timestamps.

**Investigate:**

1. `curl -s http://localhost:8093/health`
2. Gateway SQL: `SELECT reason, count(*) FROM quarantine GROUP BY 1 ORDER BY 2 DESC LIMIT 20`
3. Compare recent deploys of stream-processor / `shared/` contracts

**Mitigate:** Fix producers; do not silently widen QA gates; page if prod rate stays elevated >15m.

---

## 2. Circuit breaker tripped

**Symptoms:** CRITICAL incident with breaker reason; `GET /breakers` shows `open` / `half_open`; Overview gauge > 0.

**Investigate:**

1. `argusctl incidents list --status open` (or dashboard Incidents)
2. Query vehicle telemetry around trip time via gateway
3. Check per-vehicle quarantine rate
4. `curl -s http://localhost:8098/breakers`

**Mitigate:** Acknowledge as operator once owned; do **not** auto-resolve; wait for half-open success or explicit resolve after RCA.

---

## 3. Drift on `brake_pressure` (single feature)

**Symptoms:** Drift incident naming `brake_pressure`; Evidently report hit; Alertmanager warning.

**Investigate:** Copilot `query_drift_report` or drift-monitor reports volume; compare KS vs threshold; sample validated telemetry.

**Mitigate:** Confirm real fleet shift vs bad sensors; humans may `POST /v1/retraining:trigger`; refresh baseline only after DS sign-off.

---

## 4. Multi-feature drift storm

**Symptoms:** `multi_feature_drift`; fleet-level critical; many open incidents.

**Investigate:** List CRITICAL incidents; pull drifted feature list; check consumer lag / replay.

**Mitigate:** Treat as fleet-wide until proven otherwise; coordinate acks; copilot explains only — no auto resolve/retrain.

---

## 5. Gateway 403 / auth failures

**Symptoms:** Dashboard mutations fail; `argusctl` unauthorized; copilot tools fail while incident-engine direct works.

**Investigate:** Role chip (viewer vs operator); retry with `demo-operator`; gateway OPA deny logs; confirm `/v1/ping` public.

**Mitigate:** Re-login as operator/admin; rotate keys via `argusctl secrets`; never put admin keys in LLM prompts.

---

## Escalation cheat sheet

| Severity | Who | Action |
|----------|-----|--------|
| Warning quarantine | On-call | Investigate 15m; fix producers |
| Drift single feature | On-call + DS | Confirm; optional retrain |
| Multi-feature / many breakers | Incident commander | Fleet hold; coordinated ack |
| Auth outage | Platform | Keycloak / OPA / gateway |

Source files (also embedded for RAG):

- `ai-copilot/runbooks/quarantine-rate-spike.md`
- `ai-copilot/runbooks/circuit-breaker-tripped.md`
- `ai-copilot/runbooks/drift-brake-pressure.md`
- `ai-copilot/runbooks/multi-feature-drift-storm.md`
- `ai-copilot/runbooks/gateway-auth-failures.md`
