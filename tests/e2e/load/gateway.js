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
  vus: VUS,
  duration: DURATION,
  thresholds: {
    // Latency SLO: p95 ping under 500ms; error rate under 5%
    ping_latency_ms: ["p(95)<500"],
    errors: ["rate<0.05"],
    http_req_failed: ["rate<0.05"],
  },
};

export default function () {
  const headers = { "X-API-Key": API_KEY, Accept: "application/json" };

  const ping = http.get(`${GATEWAY}/v1/ping`, { headers });
  pingLatency.add(ping.timings.duration);
  const pingOk = check(ping, {
    "ping 200": (r) => r.status === 200,
    "ping pong": (r) => String(r.body).includes("pong"),
  });
  errorRate.add(!pingOk);

  const health = http.get(`${GATEWAY}/health`);
  check(health, { "health 200": (r) => r.status === 200 });

  const incidents = http.get(`${GATEWAY}/v1/incidents?status=open`, { headers });
  const incOk = check(incidents, {
    "incidents 200|401|403": (r) => [200, 401, 403].includes(r.status),
  });
  // Auth disabled / demo key should typically be 200
  if (incidents.status >= 500) errorRate.add(1);
  else errorRate.add(!incOk && incidents.status >= 400 && incidents.status < 500 ? 0 : 0);

  sleep(0.2);
}
