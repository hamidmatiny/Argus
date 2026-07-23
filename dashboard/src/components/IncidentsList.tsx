"use client";

import Link from "next/link";
import { useState } from "react";
import { IncidentActions } from "@/components/IncidentActions";
import type { ArgusRole, Incident } from "@/lib/types";

function severityClass(s?: string): string {
  const v = (s ?? "").toLowerCase();
  if (v.includes("critical")) return "text-red-700 bg-red-50";
  if (v.includes("warning")) return "text-amber-800 bg-amber-50";
  return "text-[var(--muted)] bg-black/[0.03]";
}

export function IncidentsList({
  initial,
  role,
}: {
  initial: Incident[];
  role: ArgusRole;
}) {
  const [items, setItems] = useState(initial);

  return (
    <div className="overflow-hidden rounded-xl border border-[var(--line)] bg-[var(--panel)]">
      <table className="w-full text-left text-sm" data-testid="incidents-table">
        <thead className="border-b border-[var(--line)] text-xs uppercase tracking-wide text-[var(--muted)]">
          <tr>
            <th className="px-4 py-3 font-medium">Incident</th>
            <th className="px-4 py-3 font-medium">Vehicle</th>
            <th className="px-4 py-3 font-medium">Severity</th>
            <th className="px-4 py-3 font-medium">Status</th>
            <th className="px-4 py-3 font-medium">Actions</th>
          </tr>
        </thead>
        <tbody>
          {items.length === 0 ? (
            <tr>
              <td colSpan={5} className="px-4 py-8 text-center text-[var(--muted)]">
                No incidents
              </td>
            </tr>
          ) : (
            items.map((inc) => (
              <tr key={inc.incident_id} className="border-b border-[var(--line)] last:border-0">
                <td className="px-4 py-3">
                  <Link
                    href={`/incidents/${encodeURIComponent(inc.incident_id)}`}
                    className="font-medium text-[var(--accent)] hover:underline"
                  >
                    {inc.incident_id}
                  </Link>
                  <p className="mt-0.5 max-w-md truncate text-xs text-[var(--muted)]">
                    {inc.reason ?? inc.summary ?? "—"}
                  </p>
                </td>
                <td className="px-4 py-3 tabular-nums">{inc.vehicle_id ?? "—"}</td>
                <td className="px-4 py-3">
                  <span className={`rounded px-1.5 py-0.5 text-xs ${severityClass(inc.severity)}`}>
                    {(inc.severity ?? "unknown").replace(/INCIDENT_SEVERITY_/g, "")}
                  </span>
                </td>
                <td className="px-4 py-3 text-xs uppercase tracking-wide">
                  {(inc.status ?? "—").replace(/INCIDENT_STATUS_/g, "")}
                </td>
                <td className="px-4 py-3">
                  <IncidentActions
                    incident={inc}
                    role={role}
                    onUpdated={(next) =>
                      setItems((prev) =>
                        prev.map((p) => (p.incident_id === next.incident_id ? { ...p, ...next } : p)),
                      )
                    }
                  />
                </td>
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  );
}
