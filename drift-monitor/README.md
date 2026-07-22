# drift-monitor

ML / statistical **drift detection** service. Compares live feature and prediction distributions against training baselines (MLflow-backed) and emits drift signals to the incident engine.

**Status:** Scaffold only — implemented in a later phase.

**Language:** Python

**Responsibilities (planned):**
- Feature and prediction drift (PSI, KS, embedding distance, etc.)
- Scheduled and streaming evaluation windows
- Alerting hooks into incident-engine and observability
