# DEMO_SCRIPT — 5-minute live walkthrough

Use this literally. Do not improvise paths. Total talk time ≈ **5:00**.

**Prep (before the call, once):**

```bash
cd Argus
cp .env.example .env
echo "NEXTAUTH_SECRET=$(openssl rand -base64 32)" >> .env
echo "NEXTAUTH_URL=http://localhost:3002" >> .env
echo "AUTH_DEMO_OFFLINE=true" >> .env
echo "LLM_PROVIDER=mock" >> .env
docker compose up -d --build
# wait until:
curl -sf http://localhost:8099/health && curl -sf http://localhost:3002/login
```

Have these tabs ready (do not share screen until :00):

1. Terminal
2. http://localhost:3002
3. http://localhost:3001 (Grafana)
4. http://localhost:8087 (Redpanda Console) — optional

---

## 0:00–0:40 — Pitch (no slides)

**Say:**  
“ARGUS is a fleet telemetry platform end-to-end: Kafka ingest, streaming QA, Iceberg lakehouse, drift detection, OPA-backed incidents, observability, an operator UI, and a read-only AI copilot. Same images locally and on EKS.”

**Show:** root README architecture diagram (or this docs Architecture page) for 5 seconds.

---

## 0:40–1:20 — Prove the bus is alive

**Run:**

```bash
curl -s http://localhost:8099/v1/ping | jq .
curl -s http://localhost:8091/health | jq .
curl -s http://localhost:8093/health | jq .
```

**Say:**  
“Simulator publishes Avro into Redpanda; Ray normalizes; stream-processor is the QA gate — validated vs quarantine.”

**Optional click:** Redpanda Console → Topics → `telemetry.validated` / `telemetry.quarantine`.

---

## 1:20–2:20 — Operator dashboard

**Open:** http://localhost:3002  

**Click:** Sign in as `operator` / `operator` (offline demo) or Keycloak demo user.

**Click through (15–20s each):**

1. **Overview** — live throughput / open breakers / health  
2. **Incidents** — open list; click one detail if present  
3. **Data Quality** — drift / QA signals  
4. **Telemetry** — run a small query if UI allows  

**Say:**  
“UI never talks to Kafka or Trino directly — only through the gateway with OPA roles. Viewers can’t ack; operators can.”

!!! note "Screenshot drop zone"
    Record GIF: `docs/assets/screenshots/demo-dashboard.gif` (TODO — capture after login → Overview → Incidents).

---

## 2:20–3:10 — Grafana SLOs

**Open:** http://localhost:3001 (admin / password from `.env` `GRAFANA_ADMIN_PASSWORD`)

**Click:** Dashboards → ARGUS (or Explore → Prometheus)

**Show:** QA pass ratio / request latency / any ARGUS recording rules.

**Say:**  
“Prometheus scrapes the services; Alertmanager can fan into the incident-engine. Observability is part of the product, not an afterthought.”

!!! note "Screenshot drop zone"
    `docs/assets/screenshots/demo-grafana.png` (TODO).

---

## 3:10–4:00 — Lakehouse + API

**Run:**

```bash
curl -s -X POST http://localhost:8099/v1/telemetry/query \
  -H 'Content-Type: application/json' \
  -H 'X-API-Key: demo-viewer' \
  -d '{"sql":"SELECT vehicle_id FROM telemetry LIMIT 5","limit":5}' | jq .
```

**Say:**  
“Validated rows land in Iceberg; Trino is behind the gateway with scoped SQL. Quarantine is a first-class table, not a log file.”

If empty: “Writers may still be catching up — show `/health` on lakehouse `:8096` and retry once.”

---

## 4:00–4:40 — Copilot (read-only)

**In dashboard:** open **Ask the fleet** (or `curl` copilot):

```bash
curl -s -X POST http://localhost:8099/v1/copilot/ask \
  -H 'Content-Type: application/json' \
  -H 'X-API-Key: demo-viewer' \
  -d '{"question":"What should I do if quarantine rate spikes?"}' | jq .
```

**Say:**  
“RAG over runbooks plus live tools — but it cannot ack, resolve, or retrain. That’s intentional: LLMs don’t get the blast radius.”

---

## 4:40–5:00 — Close

**Say:**  
“Sixteen phases: contracts → data plane → lakehouse → MLOps → incidents → gateway → UI → SDKs → Terraform/Helm/Argo → copilot → CI with coverage, Trivy, SBOM, e2e/load/chaos. Docs and ADRs explain every major trade-off. Happy to go deep on any layer.”

**Stop screen share.** Leave stack up for Q&A (`docker compose ps`).

---

## Backup one-liners (if something is down)

| Failure | Recovery |
|---------|----------|
| Dashboard 500 | Check `NEXTAUTH_SECRET` in `.env`; `docker compose up -d dashboard` |
| Gateway down | `docker compose up -d api-gateway keycloak` |
| No telemetry rows | Wait 60s; `docker compose logs lakehouse-writer --tail=30` |
| Copilot empty | `LLM_PROVIDER=mock`; `docker compose up -d qdrant ai-copilot` |
