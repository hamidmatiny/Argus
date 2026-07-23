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

export async function gatewayFetch(
  path: string,
  init: RequestInit = {},
): Promise<Response> {
  const session = await getServerSession(authOptions);
  const headers = new Headers(init.headers);
  headers.set("Accept", "application/json");
  if (session?.accessToken && !session.accessToken.startsWith("demo:")) {
    headers.set("Authorization", `Bearer ${session.accessToken}`);
  } else if (session?.accessToken?.startsWith("demo:")) {
    const user = session.accessToken.slice("demo:".length);
    const key =
      user === "admin"
        ? "demo-admin"
        : user === "operator"
          ? "demo-operator"
          : "demo-viewer";
    headers.set("X-API-Key", key);
  } else if (process.env.ARGUS_GATEWAY_API_KEY) {
    headers.set("X-API-Key", process.env.ARGUS_GATEWAY_API_KEY);
  }
  return fetch(`${getGatewayBase()}${path}`, {
    ...init,
    headers,
    cache: "no-store",
  });
}

export async function listIncidents(status?: string): Promise<Incident[]> {
  const q = status ? `?status=${encodeURIComponent(status)}` : "";
  const res = await gatewayFetch(`/v1/incidents${q}`);
  if (!res.ok) {
    throw new Error(`incidents ${res.status}`);
  }
  const data = (await res.json()) as { incidents?: Incident[] };
  return data.incidents ?? [];
}

export async function queryTelemetry(
  sql: string,
  limit = 50,
): Promise<TelemetryQueryResult> {
  const res = await gatewayFetch("/v1/telemetry/query", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ sql, limit }),
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`telemetry query ${res.status}: ${text}`);
  }
  return (await res.json()) as TelemetryQueryResult;
}

export async function fetchPrometheusInstant(
  expr: string,
): Promise<number | null> {
  const base =
    process.env.PROMETHEUS_URL ?? "http://localhost:9090";
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
