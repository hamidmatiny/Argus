import { afterEach, describe, expect, it, vi } from "vitest";
import { ArgusAPIError, ArgusAuthError, ArgusClient } from "../src/index.js";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("ArgusClient", () => {
  it("lists incidents", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          incidents: [{ incident_id: "esc_1", vehicle_id: "VH-1" }],
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
    );
    const client = new ArgusClient({
      baseUrl: "http://gateway.test",
      apiKey: "demo-viewer",
      fetch: fetchMock as unknown as typeof fetch,
    });
    const items = await client.listIncidents("open");
    expect(items[0]?.incident_id).toBe("esc_1");
    expect(fetchMock).toHaveBeenCalledWith(
      "http://gateway.test/v1/incidents?status=open",
      expect.objectContaining({ cache: "no-store" }),
    );
  });

  it("acknowledges incident", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          incident: { incident_id: "esc_1", status: "INCIDENT_STATUS_ACKNOWLEDGED" },
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
    );
    const client = new ArgusClient({
      baseUrl: "http://gateway.test",
      apiKey: "demo-operator",
      fetch: fetchMock as unknown as typeof fetch,
    });
    const inc = await client.acknowledgeIncident("esc_1", "note");
    expect(inc.status).toBe("INCIDENT_STATUS_ACKNOWLEDGED");
  });

  it("throws on 401", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response("nope", { status: 401 }));
    const client = new ArgusClient({
      baseUrl: "http://gateway.test",
      fetch: fetchMock as unknown as typeof fetch,
    });
    await expect(client.listIncidents()).rejects.toBeInstanceOf(ArgusAuthError);
  });

  it("throws ArgusAPIError on 500", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response("boom", { status: 500 }));
    const client = new ArgusClient({
      baseUrl: "http://gateway.test",
      apiKey: "demo-viewer",
      fetch: fetchMock as unknown as typeof fetch,
    });
    await expect(client.queryTelemetry("SELECT 1")).rejects.toBeInstanceOf(ArgusAPIError);
  });

  it("streams NDJSON telemetry", async () => {
    const body = new ReadableStream({
      start(controller) {
        controller.enqueue(
          new TextEncoder().encode('{"event":{"vehicle_id":"VH-1"}}\n'),
        );
        controller.enqueue(
          new TextEncoder().encode('{"event":{"vehicle_id":"VH-2"}}\n'),
        );
        controller.close();
      },
    });
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(body, { status: 200, headers: { "Content-Type": "application/json" } }),
    );
    const client = new ArgusClient({
      baseUrl: "http://gateway.test",
      apiKey: "demo-viewer",
      fetch: fetchMock as unknown as typeof fetch,
    });
    const rows: unknown[] = [];
    for await (const row of client.streamTelemetry()) {
      rows.push(row);
    }
    expect(rows).toHaveLength(2);
  });
});
