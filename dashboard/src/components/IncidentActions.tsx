"use client";

import { useState } from "react";
import { canMutateIncidents, type ArgusRole, type Incident } from "@/lib/types";

export function IncidentActions({
  incident,
  role,
  onUpdated,
}: {
  incident: Incident;
  role: ArgusRole;
  onUpdated?: (incident: Incident) => void;
}) {
  const [busy, setBusy] = useState<"ack" | "resolve" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const allowed = canMutateIncidents(role);

  if (!allowed) {
    return (
      <p className="text-xs text-[var(--muted)]" data-testid="viewer-no-actions">
        View-only — operator role required for actions
      </p>
    );
  }

  async function act(kind: "ack" | "resolve") {
    setBusy(kind);
    setError(null);
    try {
      const path =
        kind === "ack"
          ? `/api/gateway/v1/incidents/${encodeURIComponent(incident.incident_id)}/acknowledge`
          : `/api/gateway/v1/incidents/${encodeURIComponent(incident.incident_id)}/resolve`;
      const res = await fetch(path, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: kind === "ack" ? JSON.stringify({ note: "acked from dashboard" }) : undefined,
      });
      if (!res.ok) {
        throw new Error(await res.text());
      }
      const data = (await res.json()) as { incident?: Incident };
      if (data.incident) onUpdated?.(data.incident);
    } catch (err) {
      setError(err instanceof Error ? err.message : "action failed");
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="flex flex-wrap items-center gap-2" data-testid="incident-actions">
      <button
        type="button"
        data-testid="ack-button"
        disabled={busy !== null}
        onClick={() => act("ack")}
        className="rounded-md bg-[var(--accent)] px-3 py-1.5 text-sm text-white disabled:opacity-50"
      >
        {busy === "ack" ? "Acking…" : "Acknowledge"}
      </button>
      <button
        type="button"
        data-testid="resolve-button"
        disabled={busy !== null}
        onClick={() => act("resolve")}
        className="rounded-md border border-[var(--line)] bg-white px-3 py-1.5 text-sm disabled:opacity-50"
      >
        {busy === "resolve" ? "Resolving…" : "Resolve"}
      </button>
      {error ? <p className="text-xs text-red-700">{error}</p> : null}
    </div>
  );
}
