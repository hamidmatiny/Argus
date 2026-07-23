# @argus/sdk

Typed TypeScript client for the ARGUS **api-gateway** (browser + Node 18+).

## Install

```bash
# From the monorepo (dashboard uses this path)
cd sdk/typescript && npm install && npm run build

# Or as a workspace dependency
npm install @argus/sdk@file:../sdk/typescript
```

## Quickstart

```ts
import { ArgusClient } from "@argus/sdk";

const client = new ArgusClient({
  baseUrl: "http://localhost:8099",
  apiKey: "demo-operator",
});

const incidents = await client.listIncidents("open");
await client.acknowledgeIncident(incidents[0]!.incident_id, "acked");

const rows = await client.queryTelemetry(
  "SELECT vehicle_id, speed_mph FROM telemetry LIMIT 10",
);

for await (const msg of client.streamTelemetry()) {
  console.log(msg);
  break;
}
```

Env: `ARGUS_GATEWAY_URL`, `ARGUS_API_KEY` / `ARGUS_TOKEN`.

## Dashboard usage

The Phase 10 dashboard depends on `@argus/sdk` for gateway REST calls so
operator UI and external consumers share one client.
