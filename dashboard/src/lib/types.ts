export type ArgusRole = "viewer" | "operator" | "admin";

export type Incident = {
  incident_id: string;
  vehicle_id?: string;
  severity?: string;
  status?: string;
  source_service?: string;
  timestamp?: string;
  reason?: string;
  summary?: string;
  open?: boolean;
};

export type TelemetryQueryResult = {
  columns: string[];
  rows: Record<string, unknown>[];
  row_count: number;
};

export type ThroughputPoint = {
  t: string;
  eps: number;
};

export function normalizeRole(roles: string[] | undefined): ArgusRole {
  const set = new Set((roles ?? []).map((r) => r.toLowerCase()));
  if (set.has("admin")) return "admin";
  if (set.has("operator")) return "operator";
  return "viewer";
}

export function canMutateIncidents(role: ArgusRole | undefined): boolean {
  return role === "operator" || role === "admin";
}
