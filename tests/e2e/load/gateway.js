// k6 load test against api-gateway — latency SLO gate.
// Usage: k6 run -e GATEWAY_URL=http://localhost:8099 -e API_KEY=demo-viewer tests/e2e/load/gateway.js
import http from "k6/http";
import { check, sleep } from "k6";
import { Rate, Trend } from "k6/metrics";

const GATEWAY = __ENV.GATEWAY_URL || "http://localhost:8099";
const API_KEY = __ENV.API_KEY || "demo-viewer";
const VUS = Number(__ENV.VUS || 10);
const DURATION = __ENV.DURATION || "2m";

const errorRate = new Rate("errors");
const pingLatency = new Trend("ping_latency_ms", true);

export const options = {
  scenarios: {
    // Short warmup so cold JWT/handler paths are not mixed into SLO samples.
    warmup: {
      executor: "constant-vus",
      vus: Math.min(2, VUS),
      duration: "15s",
      gracefulStop: "5s",
      startTime: "0s",
      tags: { phase: "warmup" },
      exec: "traffic",
    },
    load: {
      executor: "constant-vus",
      vus: VUS,
      duration: DURATION,
      gracefulStop: "30s",
      startTime: "15s",
      tags: { phase: "load" },
      exec: "traffic",
    },
  },
  thresholds: {
    // Latency SLO: p95 ping under 500ms; error rate under 5% (load phase only).
    "ping_latency_ms{phase:load}": ["p(95)<500"],
    "errors{phase:load}": ["rate<0.05"],
    "http_req_failed{phase:load}": ["rate<0.05"],
  },
};

const headers = { "X-API-Key": API_KEY, Accept: "application/json" };

export function traffic() {
  const ping = http.get(`${GATEWAY}/v1/ping`, { headers });
  pingLatency.add(ping.timings.duration);
  const pingOk = check(ping, {
    "ping 200": (r) => r.status === 200,
    "ping pong": (r) => String(r.body).includes("pong"),
  });
  errorRate.add(!pingOk);

  const health = http.get(`${GATEWAY}/health`);
  check(health, { "health 200": (r) => r.status === 200 });

  // Auth'd route — mark 200 as the expected success for http_req_failed accounting.
  // (429 would also fail the SLO; Load Nightly raises gateway RPS so this stays green.)
  const incidents = http.get(`${GATEWAY}/v1/incidents?status=open`, {
    headers,
    responseCallback: http.expectedStatuses(200),
  });
  const incOk = check(incidents, {
    "incidents 200": (r) => r.status === 200,
  });
  errorRate.add(!incOk);

  sleep(0.2);
}
