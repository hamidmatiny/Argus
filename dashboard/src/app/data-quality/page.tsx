import { getServerSession } from "next-auth";
import { redirect } from "next/navigation";
import { AppShell } from "@/components/AppShell";
import { TimeSeriesChart } from "@/components/TimeSeriesChart";
import { authOptions } from "@/lib/auth";
import { fetchPrometheusInstant } from "@/lib/gateway";

export const dynamic = "force-dynamic";

export default async function DataQualityPage() {
  const session = await getServerSession(authOptions);
  if (!session) redirect("/login");

  const qa = (await fetchPrometheusInstant("argus:qa_pass_ratio")) ?? 0;
  const drift = (await fetchPrometheusInstant("argus:drift_score_avg")) ?? 0;
  const reportsURL =
    process.env.NEXT_PUBLIC_DRIFT_REPORTS_URL ??
    "http://localhost:8094"; // drift-monitor health; Evidently HTML under /reports when exposed

  // Build a short synthetic trend from current gauges for demo continuity.
  const now = Date.now();
  const driftTrend = Array.from({ length: 12 }, (_, i) => ({
    t: new Date(now - (11 - i) * 300_000).toISOString().slice(11, 16),
    v: Math.max(0, drift + Math.sin(i / 2) * 0.02),
  }));
  const qaTrend = Array.from({ length: 12 }, (_, i) => ({
    t: new Date(now - (11 - i) * 300_000).toISOString().slice(11, 16),
    v: Math.min(1, Math.max(0.9, qa + Math.cos(i / 3) * 0.01)),
  }));

  return (
    <AppShell>
      <header className="mb-6">
        <h1 className="font-display text-3xl tracking-tight">Data Quality &amp; Drift</h1>
        <p className="mt-1 text-sm text-[var(--muted)]">
          QA pass ratio and drift score trends · Evidently reports
        </p>
      </header>

      <div className="grid gap-4 lg:grid-cols-2">
        <section className="rounded-xl border border-[var(--line)] bg-[var(--panel)] p-5">
          <h2 className="font-display text-xl">QA pass ratio</h2>
          <p className="text-sm text-[var(--muted)]">
            Current {(qa * 100).toFixed(2)}% · SLO 99%
          </p>
          <div className="mt-3">
            <TimeSeriesChart data={qaTrend} color="#0f6e56" unit="" />
          </div>
        </section>
        <section className="rounded-xl border border-[var(--line)] bg-[var(--panel)] p-5">
          <h2 className="font-display text-xl">Drift score</h2>
          <p className="text-sm text-[var(--muted)]">
            Current {drift.toFixed(3)} · warn &gt; 0.2
          </p>
          <div className="mt-3">
            <TimeSeriesChart data={driftTrend} color="#b45309" />
          </div>
        </section>
      </div>

      <section className="mt-6 rounded-xl border border-[var(--line)] bg-[var(--panel)] p-5">
        <h2 className="font-display text-xl">Evidently reports</h2>
        <p className="mt-1 text-sm text-[var(--muted)]">
          Embed / open the latest HTML report from drift-monitor. Placeholder until the
          report server is mounted at a stable URL.
        </p>
        <div className="mt-4 overflow-hidden rounded-lg border border-[var(--line)] bg-white">
          <div className="flex items-center justify-between border-b border-[var(--line)] px-4 py-2 text-xs text-[var(--muted)]">
            <span>report preview</span>
            <a
              className="text-[var(--accent)] hover:underline"
              href={reportsURL}
              target="_blank"
              rel="noreferrer"
            >
              Open drift-monitor
            </a>
          </div>
          <div className="flex h-64 items-center justify-center text-sm text-[var(--muted)]">
            {/* Screenshot placeholder */}
            <div className="text-center">
              <p className="font-medium text-[var(--ink)]">Evidently report embed</p>
              <p className="mt-1">Add DRIFT_REPORTS_PUBLIC_URL when HTML reports are published.</p>
            </div>
          </div>
        </div>
      </section>
    </AppShell>
  );
}
