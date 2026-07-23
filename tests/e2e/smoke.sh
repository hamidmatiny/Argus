#!/usr/bin/env bash
# Full-stack smoke: boot compose, run simulator traffic, assert gateway + lakehouse signals.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

# Note: docker-compose.yml uses fixed container_name: argus-* so only one
# stack can run at a time (COMPOSE_PROJECT_NAME alone does not isolate).
export AUTH_DEMO_OFFLINE="${AUTH_DEMO_OFFLINE:-true}"
export LLM_PROVIDER="${LLM_PROVIDER:-mock}"
export EMBEDDING_PROVIDER="${EMBEDDING_PROVIDER:-hash}"
export API_GATEWAY_AUTH_DISABLED="${API_GATEWAY_AUTH_DISABLED:-true}"

SIM_SECONDS="${SIM_SECONDS:-60}"
GATEWAY="${GATEWAY_URL:-http://localhost:8099}"
API_KEY="${ARGUS_API_KEY:-demo-viewer}"
# Nightly sets E2E_STRICT=1 — require telemetry rows + a QA rejection signal.
E2E_STRICT="${E2E_STRICT:-1}"

cleanup() {
  echo "==> teardown"
  docker compose down -v --remove-orphans || true
}
trap cleanup EXIT

echo "==> preflight: stop any existing ARGUS compose stack"
docker compose down --remove-orphans || true

echo "==> ensure .env"
if [[ ! -f .env ]]; then
  cp .env.example .env
fi
if ! grep -q '^NEXTAUTH_SECRET=.\+' .env 2>/dev/null; then
  echo "NEXTAUTH_SECRET=$(openssl rand -base64 32)" >> .env
fi
if ! grep -q '^NEXTAUTH_URL=' .env 2>/dev/null; then
  echo "NEXTAUTH_URL=http://localhost:3002" >> .env
fi
# Ensure simulator injects some invalid events for quarantine assertions.
if ! grep -q '^SIMULATOR_FAILURE_RATE=' .env 2>/dev/null; then
  echo "SIMULATOR_FAILURE_RATE=0.15" >> .env
fi

echo "==> compose up (build + wait for healthchecks)"
# Do not fall back to a wait-less `up` — that races the dashboard health sweep.
docker compose up -d --build --wait

echo "==> wait for gateway"
ready=0
for i in $(seq 1 60); do
  if curl -sf "$GATEWAY/health" >/dev/null; then
    echo "gateway ready (${i})"
    ready=1
    break
  fi
  sleep 5
done
[[ "$ready" -eq 1 ]] || { echo "gateway never became healthy"; exit 1; }
curl -sf "$GATEWAY/health" | tee /tmp/e2e-gateway-health.json

wait_url() {
  local url="$1"
  local attempts="${2:-36}"
  local i
  for i in $(seq 1 "$attempts"); do
    if curl -sf --max-time 10 "$url" >/dev/null; then
      echo "OK  $url (attempt ${i})"
      return 0
    fi
    sleep 5
  done
  echo "FAIL $url (after ${attempts} attempts)"
  return 1
}

echo "==> health sweep"
fail=0
for url in \
  "http://localhost:8091/health" \
  "http://localhost:8092/health" \
  "http://localhost:8093/health" \
  "http://localhost:8094/health" \
  "http://localhost:8096/health" \
  "http://localhost:8098/health" \
  "http://localhost:8099/health" \
  "http://localhost:8090/health" \
  "http://localhost:3002/login"
do
  # Dashboard (Next.js) often needs tens of seconds after container start.
  if [[ "$url" == *":3002/"* ]]; then
    wait_url "$url" 48 || fail=1
  else
    wait_url "$url" 12 || fail=1
  fi
done

echo "==> wait ${SIM_SECONDS}s for simulator traffic"
sleep "$SIM_SECONDS"

echo "==> assert telemetry via gateway"
QUERY_BODY='{"sql":"SELECT vehicle_id FROM telemetry LIMIT 5","limit":5}'
code=$(curl -sS -o /tmp/e2e-telemetry.json -w "%{http_code}" \
  -X POST "$GATEWAY/v1/telemetry/query" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $API_KEY" \
  -d "$QUERY_BODY" || true)
echo "telemetry_query status=$code"
cat /tmp/e2e-telemetry.json || true

curl -sf "$GATEWAY/v1/ping" | tee /tmp/e2e-ping.json

echo "==> assert QA rejection signal (quarantine query and/or Prometheus)"
Q_BODY='{"sql":"SELECT count(*) AS c FROM quarantine","limit":1}'
qcode=$(curl -sS -o /tmp/e2e-quarantine.json -w "%{http_code}" \
  -X POST "$GATEWAY/v1/telemetry/query" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $API_KEY" \
  -d "$Q_BODY" || true)
echo "quarantine_query status=$qcode"
cat /tmp/e2e-quarantine.json || true

# Prometheus QA reject counter (name may vary; try common ARGUS series)
for q in \
  'argus_qa_reject_total' \
  'argus:qa_reject_total' \
  'qa_reject_total' \
  'argus_stream_processor_rejected_total'
do
  # Sanitize metric names for on-disk paths (GitHub Actions artifacts forbid ':').
  safe_q="$(printf '%s' "$q" | tr ':"<>|*?/\r\n' '___________')"
  out="/tmp/e2e-prom-${safe_q}.json"
  if curl -sfG "http://localhost:9090/api/v1/query" --data-urlencode "query=${q}" -o "$out" 2>/dev/null; then
    echo "prom query ${q} -> ${out}:"
    cat "$out" || true
  fi
done
# Also scrape stream-processor metrics if exposed
curl -sf "http://localhost:8093/metrics" -o /tmp/e2e-qa-metrics.txt 2>/dev/null || true

export E2E_STRICT TELEMETRY_HTTP="$code" QUARANTINE_HTTP="$qcode"
python3 - <<'PY'
import json, os, re, sys

strict = os.environ.get("E2E_STRICT", "1") == "1"
ping = json.load(open("/tmp/e2e-ping.json"))
assert ping.get("pong") is True, ping

def row_count(path: str) -> int:
    try:
        data = json.load(open(path))
    except Exception:
        return 0
    if isinstance(data, dict):
        if isinstance(data.get("rows"), list):
            return len(data["rows"])
        if isinstance(data.get("data"), list):
            return len(data["data"])
        # nested result shapes
        for key in ("result", "results", "items"):
            v = data.get(key)
            if isinstance(v, list):
                return len(v)
    if isinstance(data, list):
        return len(data)
    return 0

tele_rows = row_count("/tmp/e2e-telemetry.json")
quar_rows = row_count("/tmp/e2e-quarantine.json")

reject_signal = False
# Quarantine table non-empty
if quar_rows > 0:
    reject_signal = True
# Or Prometheus vector > 0
for name in os.listdir("/tmp"):
    if not name.startswith("e2e-prom-"):
        continue
    try:
        p = json.load(open(f"/tmp/{name}"))
        for r in p.get("data", {}).get("result", []) or []:
            val = float((r.get("value") or [0, "0"])[1])
            if val > 0:
                reject_signal = True
    except Exception:
        pass
# Or metrics scrape
try:
    text = open("/tmp/e2e-qa-metrics.txt").read()
    for line in text.splitlines():
        if line.startswith("#") or not line.strip():
            continue
        if not re.search(r"reject|quarantine", line, re.I):
            continue
        parts = line.split()
        if parts and re.fullmatch(r"[0-9]+(\.[0-9]+)?", parts[-1]) and float(parts[-1]) > 0:
            reject_signal = True
except FileNotFoundError:
    pass

print(f"telemetry_rows={tele_rows} quarantine_rows={quar_rows} reject_signal={reject_signal}")

if strict:
    if tele_rows < 1 and os.environ.get("TELEMETRY_HTTP") != "200":
        print("STRICT: telemetry query failed and no rows", file=sys.stderr)
        sys.exit(1)
    if tele_rows < 1:
        # HTTP 200 with empty rows still fails strict — lakehouse must have data
        print("STRICT: expected telemetry rows in lakehouse via gateway", file=sys.stderr)
        sys.exit(1)
    if not reject_signal:
        print("STRICT: expected at least one QA rejection signal", file=sys.stderr)
        sys.exit(1)

print("e2e_smoke_ok")
PY

if [[ "$fail" -ne 0 ]]; then
  echo "health sweep had failures"
  exit 1
fi

echo "==> e2e smoke passed"
