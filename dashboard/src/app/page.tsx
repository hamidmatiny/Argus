import { getServerSession } from "next-auth";
import { redirect } from "next/navigation";
import { AppShell } from "@/components/AppShell";
import { LiveThroughput } from "@/components/LiveThroughput";
import { authOptions } from "@/lib/auth";
import { fetchPrometheusInstant, listIncidents } from "@/lib/gateway";
import { normalizeRole } from "@/lib/types";

export const dynamic = "force-dynamic";

export default async function OverviewPage() {
  const session = await getServerSession(authOptions);
  if (!session) redirect("/login");

  let openIncidents = 0;
  let incidentError: string | null = null;
  try {
    const incidents = await listIncidents("open");
    openIncidents = incidents.length;
  } catch (err) {
    incidentError = err instanceof Error ? err.message : "incidents unavailable";
  }

  const qa =
    (await fetchPrometheusInstant("argus:qa_pass_ratio")) ?? null;
  const drift =
    (await fetchPrometheusInstant("argus:drift_score_avg")) ?? null;
  const breakers =
    (await fetchPrometheusInstant("argus:breakers_open")) ?? null;

  return (
    <AppShell>
      <header className="mb-6">
        <h1 className="font-display text-3xl tracking-tight">Overview</h1>
        <p className="mt-1 text-sm text-[var(--muted)]">
          Fleet health summary for{" "}
          <span className="text-[var(--ink)]">{session.user?.name}</span> (
          {normalizeRole(session.roles)})
        </p>
      </header>

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <Stat
          label="Open incidents"
          value={incidentError ? "—" : String(openIncidents)}
          hint={incidentError ?? "from api-gateway"}
          warn={openIncidents > 0}
        />
        <Stat
          label="QA pass ratio"
          value={qa == null ? "—" : `${(qa * 100).toFixed(1)}%`}
          hint="SLO ≥ 99%"
          warn={qa != null && qa < 0.99}
        />
        <Stat
          label="Avg drift score"
          value={drift == null ? "—" : drift.toFixed(3)}
          hint="warn &gt; 0.2"
          warn={drift != null && drift > 0.2}
        />
        <Stat
          label="Open breakers"
          value={breakers == null ? "—" : String(Math.round(breakers))}
          hint="circuit breakers"
          warn={breakers != null && breakers > 0}
        />
      </div>

      <div className="mt-6">
        <LiveThroughput />
      </div>
    </AppShell>
  );
}

function Stat({
  label,
  value,
  hint,
  warn,
}: {
  label: string;
  value: string;
  hint: string;
  warn?: boolean;
}) {
  return (
    <div
      className={`rounded-xl border bg-[var(--panel)] p-4 ${
        warn ? "border-amber-400/70" : "border-[var(--line)]"
      }`}
      data-testid={`stat-${label.toLowerCase().replace(/\s+/g, "-")}`}
    >
      <p className="text-xs uppercase tracking-[0.14em] text-[var(--muted)]">{label}</p>
      <p className="mt-2 font-display text-3xl tabular-nums">{value}</p>
      <p className="mt-1 text-xs text-[var(--muted)]">{hint}</p>
    </div>
  );
}
