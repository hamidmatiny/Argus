import { ArgusClient } from "@argus/sdk";
import { getServerSession } from "next-auth";
import { authOptions } from "@/lib/auth";
import type { Incident, TelemetryQueryResult } from "@/lib/types";

const gatewayURL =
  process.env.ARGUS_GATEWAY_URL ??
  process.env.NEXT_PUBLIC_ARGUS_GATEWAY_URL ??
  "http://localhost:8099";

export function getGatewayBase(): string {
  return gatewayURL.replace(/\/$/, "");
}

async function sessionAuth(): Promise<{ apiKey?: string; token?: string }> {
  const session = await getServerSession(authOptions);
  if (session?.accessToken && !session.accessToken.startsWith("demo:")) {
    return { token: session.accessToken };
  }
  if (session?.accessToken?.startsWith("demo:")) {
    const user = session.accessToken.slice("demo:".length);
    const apiKey =
      user === "admin"
        ? "demo-admin"
        : user === "operator"
          ? "demo-operator"
          : "demo-viewer";
    return { apiKey };
  }
  if (process.env.ARGUS_GATEWAY_API_KEY) {
    return { apiKey: process.env.ARGUS_GATEWAY_API_KEY };
  }
  return {};
}

/** Server-side ArgusClient bound to the current NextAuth session. */
export async function getArgusClient(): Promise<ArgusClient> {
  const auth = await sessionAuth();
  return new ArgusClient({
    baseUrl: getGatewayBase(),
    apiKey: auth.apiKey,
    token: auth.token,
  });
}

/** Low-level fetch still used by the SSE bridge (streaming Response body). */
export async function gatewayFetch(
  path: string,
  init: RequestInit = {},
): Promise<Response> {
  const client = await getArgusClient();
  const headers = new Headers(init.headers);
  headers.set("Accept", "application/json");
  // Mirror ArgusClient auth onto this one-off fetch.
  const auth = await sessionAuth();
  if (auth.token) headers.set("Authorization", `Bearer ${auth.token}`);
  else if (auth.apiKey) headers.set("X-API-Key", auth.apiKey);
  return fetch(`${client.baseUrl}${path}`, {
    ...init,
    headers,
    cache: "no-store",
  });
}

export async function listIncidents(status?: string): Promise<Incident[]> {
  const client = await getArgusClient();
  return client.listIncidents(status);
}

export async function queryTelemetry(
  sql: string,
  limit = 50,
): Promise<TelemetryQueryResult> {
  const client = await getArgusClient();
  return client.queryTelemetry(sql, limit);
}

export async function fetchPrometheusInstant(
  expr: string,
): Promise<number | null> {
  const base = process.env.PROMETHEUS_URL ?? "http://localhost:9090";
  try {
    const url = `${base}/api/v1/query?query=${encodeURIComponent(expr)}`;
    const res = await fetch(url, { cache: "no-store" });
    if (!res.ok) return null;
    const data = (await res.json()) as {
      data?: { result?: { value: [number, string] }[] };
    };
    const v = data.data?.result?.[0]?.value?.[1];
    return v != null ? Number(v) : null;
  } catch {
    return null;
  }
}
