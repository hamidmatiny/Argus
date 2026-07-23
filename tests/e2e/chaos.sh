#!/usr/bin/env bash
# Chaos smoke: SIGKILL a critical service and assert it recovers healthy.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

TARGET="${CHAOS_SERVICE:-stream-processor}"
HEALTH_URL="${CHAOS_HEALTH_URL:-http://localhost:8093/health}"
GATEWAY="${GATEWAY_URL:-http://localhost:8099}"

echo "==> pre-chaos health"
curl -sf "$HEALTH_URL" >/dev/null
curl -sf "$GATEWAY/health" >/dev/null

echo "==> kill ${TARGET}"
cid="$(docker compose ps -q "$TARGET")"
if [[ -z "$cid" ]]; then
  echo "service ${TARGET} not running"
  exit 1
fi
docker kill "$cid"
sleep 2

echo "==> wait for compose recreate / health"
recovered=0
for i in $(seq 1 60); do
  if curl -sf --max-time 3 "$HEALTH_URL" >/dev/null; then
    echo "recovered after ${i} attempts"
    recovered=1
    break
  fi
  # restart policy / compose may leave it exited — nudge it
  if (( i % 10 == 0 )); then
    docker compose up -d "$TARGET" || true
  fi
  sleep 3
done

if [[ "$recovered" -ne 1 ]]; then
  echo "FAILED: ${TARGET} did not recover"
  docker compose ps "$TARGET" || true
  docker compose logs --tail=80 "$TARGET" || true
  exit 1
fi

echo "==> gateway still healthy"
curl -sf "$GATEWAY/health" | tee /tmp/e2e-chaos-gateway.json
echo "chaos_ok"
