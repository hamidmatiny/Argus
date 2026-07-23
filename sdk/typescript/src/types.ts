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

export type RetrainResponse = {
  run_id?: string;
  status?: string;
  message?: string;
};

export type ArgusClientOptions = {
  baseUrl?: string;
  apiKey?: string;
  token?: string;
  /** Injected fetch (tests / custom agents). Defaults to global fetch. */
  fetch?: typeof fetch;
};
