"use client";

import { FormEvent, useState } from "react";
import { AppShell } from "@/components/AppShell";
import type { TelemetryQueryResult } from "@/lib/types";

export default function TelemetryExplorerPage() {
  const [sql, setSql] = useState(
    "SELECT vehicle_id, speed_mph, gps_lat, gps_lon, timestamp FROM telemetry ORDER BY timestamp DESC LIMIT 50",
  );
  const [result, setResult] = useState<TelemetryQueryResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const res = await fetch("/api/gateway/v1/telemetry/query", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ sql, limit: 100 }),
      });
      if (!res.ok) throw new Error(await res.text());
      setResult((await res.json()) as TelemetryQueryResult);
    } catch (err) {
      setResult(null);
      setError(err instanceof Error ? err.message : "query failed");
    } finally {
      setBusy(false);
    }
  }

  const points =
    result?.rows
      ?.map((row) => ({
        id: String(row.vehicle_id ?? ""),
        lat: Number(row.gps_lat),
        lon: Number(row.gps_lon),
      }))
      .filter((p) => Number.isFinite(p.lat) && Number.isFinite(p.lon)) ?? [];

  return (
    <AppShell>
      <header className="mb-6">
        <h1 className="font-display text-3xl tracking-tight">Telemetry Explorer</h1>
        <p className="mt-1 text-sm text-[var(--muted)]">
          Lakehouse SQL via api-gateway → Trino
        </p>
      </header>

      <form onSubmit={onSubmit} className="rounded-xl border border-[var(--line)] bg-[var(--panel)] p-4">
        <textarea
          className="min-h-28 w-full rounded-md border border-[var(--line)] bg-white p-3 font-mono text-sm"
          value={sql}
          onChange={(e) => setSql(e.target.value)}
        />
        <button
          type="submit"
          disabled={busy}
          className="mt-3 rounded-md bg-[var(--accent)] px-4 py-2 text-sm text-white disabled:opacity-50"
        >
          {busy ? "Running…" : "Run query"}
        </button>
        {error ? <p className="mt-2 text-sm text-red-700">{error}</p> : null}
      </form>

      {result ? (
        <div className="mt-6 grid gap-4 lg:grid-cols-[1.4fr_1fr]">
          <div className="overflow-auto rounded-xl border border-[var(--line)] bg-[var(--panel)]">
            <table className="w-full min-w-[640px] text-left text-sm">
              <thead className="border-b border-[var(--line)] text-xs uppercase tracking-wide text-[var(--muted)]">
                <tr>
                  {result.columns.map((c) => (
                    <th key={c} className="px-3 py-2 font-medium">
                      {c}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {result.rows.map((row, i) => (
                  <tr key={i} className="border-b border-[var(--line)] last:border-0">
                    {result.columns.map((c) => (
                      <td key={c} className="px-3 py-2 tabular-nums">
                        {String(row[c] ?? "")}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="rounded-xl border border-[var(--line)] bg-[var(--panel)] p-4">
            <h2 className="font-display text-lg">Map view</h2>
            <p className="text-xs text-[var(--muted)]">
              GPS points from query result ({points.length})
            </p>
            <div className="relative mt-3 h-72 overflow-hidden rounded-lg border border-[var(--line)] bg-[#d9e4ea]">
              {points.length === 0 ? (
                <p className="flex h-full items-center justify-center text-sm text-[var(--muted)]">
                  No gps_lat/gps_lon columns in result
                </p>
              ) : (
                points.map((p, i) => {
                  const x = ((p.lon + 180) / 360) * 100;
                  const y = ((90 - p.lat) / 180) * 100;
                  return (
                    <span
                      key={`${p.id}-${i}`}
                      title={`${p.id} (${p.lat.toFixed(3)}, ${p.lon.toFixed(3)})`}
                      className="absolute h-2.5 w-2.5 -translate-x-1/2 -translate-y-1/2 rounded-full bg-[var(--accent)] shadow"
                      style={{ left: `${x}%`, top: `${y}%` }}
                    />
                  );
                })
              )}
            </div>
          </div>
        </div>
      ) : null}
    </AppShell>
  );
}
