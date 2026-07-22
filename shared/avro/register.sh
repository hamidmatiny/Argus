#!/usr/bin/env bash
# Register ARGUS Avro schemas with the local Confluent-compatible schema registry
# (Redpanda built-in SR on :18081 by default).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SCHEMA_REGISTRY_URL="${SCHEMA_REGISTRY_URL:-http://localhost:18081}"
SUBJECT_PREFIX="${ARGUS_SCHEMA_SUBJECT_PREFIX:-argus}"
SCHEMA_FILE="${ROOT}/shared/avro/telemetry_event.avsc"
SUBJECT="${SUBJECT_PREFIX}.telemetry.TelemetryEvent-value"

if [[ ! -f "${SCHEMA_FILE}" ]]; then
  echo "error: schema not found: ${SCHEMA_FILE}" >&2
  exit 1
fi

# Compact JSON for the registry API (single-line schema string).
SCHEMA_JSON="$(python3 -c 'import json,sys; print(json.dumps(json.load(open(sys.argv[1]))))' "${SCHEMA_FILE}")"
BODY="$(python3 -c 'import json,sys; print(json.dumps({"schemaType":"AVRO","schema":sys.argv[1]}))' "${SCHEMA_JSON}")"

echo "Registering ${SUBJECT} at ${SCHEMA_REGISTRY_URL} ..."
HTTP_CODE="$(curl -sS -o /tmp/argus-sr-register.json -w '%{http_code}' \
  -X POST \
  -H 'Content-Type: application/vnd.schemaregistry.v1+json' \
  --data "${BODY}" \
  "${SCHEMA_REGISTRY_URL}/subjects/${SUBJECT}/versions")"

cat /tmp/argus-sr-register.json
echo
if [[ "${HTTP_CODE}" != "200" ]]; then
  echo "error: schema registry returned HTTP ${HTTP_CODE}" >&2
  exit 1
fi
echo "OK — registered ${SUBJECT}"
