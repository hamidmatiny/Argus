import { ArgusAPIError, ArgusAuthError } from "./errors.js";
import type {
  ArgusClientOptions,
  Incident,
  RetrainResponse,
  TelemetryQueryResult,
} from "./types.js";

export class ArgusClient {
  readonly baseUrl: string;
  private readonly apiKey?: string;
  private readonly token?: string;
  private readonly fetchImpl: typeof fetch;

  constructor(opts: ArgusClientOptions = {}) {
    this.baseUrl = (
      opts.baseUrl ??
      process.env.ARGUS_GATEWAY_URL ??
      process.env.NEXT_PUBLIC_ARGUS_GATEWAY_URL ??
      "http://localhost:8099"
    ).replace(/\/$/, "");
    this.apiKey = opts.apiKey ?? process.env.ARGUS_API_KEY;
    this.token = opts.token ?? process.env.ARGUS_TOKEN;
    this.fetchImpl = opts.fetch ?? fetch.bind(globalThis);
  }

  private authHeaders(extra?: HeadersInit): Headers {
    const headers = new Headers(extra);
    headers.set("Accept", "application/json");
    if (this.token) {
      headers.set("Authorization", `Bearer ${this.token}`);
    } else if (this.apiKey) {
      headers.set("X-API-Key", this.apiKey);
    }
    return headers;
  }

  async request<T>(path: string, init: RequestInit = {}): Promise<T> {
    const res = await this.fetchImpl(`${this.baseUrl}${path}`, {
      ...init,
      headers: this.authHeaders(init.headers),
      cache: "no-store",
    });
    if (res.status === 401 || res.status === 403) {
      throw new ArgusAuthError(await res.text());
    }
    if (!res.ok) {
      throw new ArgusAPIError(res.status, await res.text());
    }
    if (res.status === 204) {
      return undefined as T;
    }
    return (await res.json()) as T;
  }

  ping(): Promise<{ pong?: boolean; ts?: string }> {
    return this.request("/v1/ping");
  }

  health(): Promise<{ status?: string; service?: string }> {
    return this.request("/health");
  }

  async listIncidents(status?: string): Promise<Incident[]> {
    const q = status ? `?status=${encodeURIComponent(status)}` : "";
    const data = await this.request<{ incidents?: Incident[] }>(`/v1/incidents${q}`);
    return data.incidents ?? [];
  }

  async acknowledgeIncident(
    incidentId: string,
    note = "",
  ): Promise<Incident> {
    const data = await this.request<{ incident: Incident }>(
      `/v1/incidents/${encodeURIComponent(incidentId)}/acknowledge`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ note }),
      },
    );
    return data.incident;
  }

  async resolveIncident(incidentId: string): Promise<Incident> {
    const data = await this.request<{ incident: Incident }>(
      `/v1/incidents/${encodeURIComponent(incidentId)}/resolve`,
      { method: "POST" },
    );
    return data.incident;
  }

  queryTelemetry(sql: string, limit = 50): Promise<TelemetryQueryResult> {
    return this.request("/v1/telemetry/query", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ sql, limit }),
    });
  }

  triggerRetraining(
    reason = "",
    tags: Record<string, string> = {},
  ): Promise<RetrainResponse> {
    return this.request("/v1/retraining:trigger", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ reason, tags }),
    });
  }

  /**
   * Async generator over NDJSON lines from GET /v1/telemetry/stream.
   */
  async *streamTelemetry(vehicleId?: string): AsyncGenerator<unknown> {
    const q = vehicleId
      ? `?vehicle_id=${encodeURIComponent(vehicleId)}`
      : "";
    const res = await this.fetchImpl(`${this.baseUrl}/v1/telemetry/stream${q}`, {
      headers: this.authHeaders(),
      cache: "no-store",
    });
    if (res.status === 401 || res.status === 403) {
      throw new ArgusAuthError(await res.text());
    }
    if (!res.ok || !res.body) {
      throw new ArgusAPIError(res.status, await res.text());
    }
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buf = "";
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buf += decoder.decode(value, { stream: true });
      const parts = buf.split("\n");
      buf = parts.pop() ?? "";
      for (const line of parts) {
        const trimmed = line.trim();
        if (!trimmed) continue;
        try {
          yield JSON.parse(trimmed) as unknown;
        } catch {
          /* skip partial/garbage */
        }
      }
    }
  }
}
