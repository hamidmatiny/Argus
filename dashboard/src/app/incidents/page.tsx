import { getServerSession } from "next-auth";
import { redirect } from "next/navigation";
import { AppShell } from "@/components/AppShell";
import { IncidentsList } from "@/components/IncidentsList";
import { authOptions } from "@/lib/auth";
import { listIncidents } from "@/lib/gateway";
import { normalizeRole, type Incident } from "@/lib/types";

export const dynamic = "force-dynamic";

export default async function IncidentsPage() {
  const session = await getServerSession(authOptions);
  if (!session) redirect("/login");
  const role = normalizeRole(session.roles);

  let incidents: Incident[] = [];
  let error: string | null = null;
  try {
    incidents = await listIncidents();
  } catch (err) {
    error = err instanceof Error ? err.message : "failed to load incidents";
  }

  return (
    <AppShell>
      <header className="mb-6">
        <h1 className="font-display text-3xl tracking-tight">Incidents</h1>
        <p className="mt-1 text-sm text-[var(--muted)]">
          Circuit-breaker escalations via api-gateway · role {role}
        </p>
      </header>
      {error ? (
        <p className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">
          {error}
        </p>
      ) : (
        <IncidentsList initial={incidents} role={role} />
      )}
    </AppShell>
  );
}
