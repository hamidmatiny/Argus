import { getServerSession } from "next-auth";
import Link from "next/link";
import { redirect } from "next/navigation";
import { AppShell } from "@/components/AppShell";
import { IncidentActions } from "@/components/IncidentActions";
import { authOptions } from "@/lib/auth";
import { listIncidents } from "@/lib/gateway";
import { normalizeRole } from "@/lib/types";

export const dynamic = "force-dynamic";

export default async function IncidentDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const session = await getServerSession(authOptions);
  if (!session) redirect("/login");
  const { id } = await params;
  const role = normalizeRole(session.roles);
  const all = await listIncidents().catch(() => []);
  const incident = all.find((i) => i.incident_id === id);

  return (
    <AppShell>
      <Link href="/incidents" className="text-sm text-[var(--accent)] hover:underline">
        ← Incidents
      </Link>
      <header className="mt-3 mb-6">
        <h1 className="font-display text-3xl tracking-tight break-all">{id}</h1>
      </header>
      {!incident ? (
        <p className="text-[var(--muted)]">Incident not found in current gateway snapshot.</p>
      ) : (
        <div className="rounded-xl border border-[var(--line)] bg-[var(--panel)] p-6 space-y-4">
          <dl className="grid gap-3 sm:grid-cols-2 text-sm">
            <div>
              <dt className="text-[var(--muted)]">Vehicle</dt>
              <dd className="font-medium">{incident.vehicle_id ?? "—"}</dd>
            </div>
            <div>
              <dt className="text-[var(--muted)]">Status</dt>
              <dd className="font-medium">{incident.status}</dd>
            </div>
            <div>
              <dt className="text-[var(--muted)]">Severity</dt>
              <dd className="font-medium">{incident.severity}</dd>
            </div>
            <div>
              <dt className="text-[var(--muted)]">Timestamp</dt>
              <dd className="font-medium">{incident.timestamp}</dd>
            </div>
            <div className="sm:col-span-2">
              <dt className="text-[var(--muted)]">Reason</dt>
              <dd className="font-medium">{incident.reason ?? incident.summary ?? "—"}</dd>
            </div>
          </dl>
          <IncidentActions incident={incident} role={role} />
        </div>
      )}
    </AppShell>
  );
}
