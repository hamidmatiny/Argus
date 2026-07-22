# incident-engine

Correlation and incident management service. Turns drift alerts, QA failures, and SLO breaches into actionable incidents with routing and severity policies.

**Status:** Scaffold only — implemented in a later phase.

**Language:** Go

**Responsibilities (planned):**
- Ingest alerts from drift-monitor, Flink QA, and OTel-derived SLOs
- Deduplicate, correlate, and escalate incidents
- Expose APIs consumed by api-gateway and dashboard
