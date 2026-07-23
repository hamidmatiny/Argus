"use client";

import { useEffect, useState } from "react";
import { AppShell } from "@/components/AppShell";

type PipelinePayload = {
  dagster: { runs: { id: string; status: string; jobName?: string }[]; error?: string };
  mlflow: {
    runs: { info?: { run_id?: string; status?: string; experiment_id?: string } }[];
    error?: string;
  };
};

export default function PipelinePage() {
  const [data, setData] = useState<PipelinePayload | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function load() {
    setError(null);
    try {
      const res = await fetch("/api/pipeline", { cache: "no-store" });
      if (!res.ok) throw new Error(await res.text());
      setData((await res.json()) as PipelinePayload);
    } catch (err) {
      setError(err instanceof Error ? err.message : "load failed");
    }
  }

  useEffect(() => {
    load();
  }, []);

  async function triggerRetrain() {
    setBusy(true);
    try {
      const res = await fetch("/api/gateway/v1/retraining:trigger", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ reason: "dashboard-manual" }),
      });
      if (!res.ok) throw new Error(await res.text());
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "retrain failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <AppShell>
      <header className="mb-6 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="font-display text-3xl tracking-tight">Pipeline Status</h1>
          <p className="mt-1 text-sm text-[var(--muted)]">
            Dagster runs and MLflow tracking
          </p>
        </div>
        <button
          type="button"
          onClick={triggerRetrain}
          disabled={busy}
          className="rounded-md bg-[var(--accent)] px-4 py-2 text-sm text-white disabled:opacity-50"
        >
          {busy ? "Launching…" : "Trigger retraining"}
        </button>
      </header>

      {error ? (
        <p className="mb-4 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">
          {error}
        </p>
      ) : null}

      <div className="grid gap-4 lg:grid-cols-2">
        <section className="rounded-xl border border-[var(--line)] bg-[var(--panel)] p-5">
          <h2 className="font-display text-xl">Dagster</h2>
          {data?.dagster.error ? (
            <p className="mt-2 text-sm text-amber-800">{data.dagster.error}</p>
          ) : null}
          <ul className="mt-3 space-y-2 text-sm">
            {(data?.dagster.runs ?? []).length === 0 ? (
              <li className="text-[var(--muted)]">No recent runs</li>
            ) : (
              data?.dagster.runs.map((r) => (
                <li
                  key={r.id}
                  className="flex items-center justify-between rounded-md border border-[var(--line)] bg-white px-3 py-2"
                >
                  <span className="truncate font-mono text-xs">{r.jobName ?? r.id}</span>
                  <span className="text-xs uppercase tracking-wide text-[var(--muted)]">
                    {r.status}
                  </span>
                </li>
              ))
            )}
          </ul>
        </section>
        <section className="rounded-xl border border-[var(--line)] bg-[var(--panel)] p-5">
          <h2 className="font-display text-xl">MLflow</h2>
          {data?.mlflow.error ? (
            <p className="mt-2 text-sm text-amber-800">{data.mlflow.error}</p>
          ) : null}
          <ul className="mt-3 space-y-2 text-sm">
            {(data?.mlflow.runs ?? []).length === 0 ? (
              <li className="text-[var(--muted)]">No recent runs</li>
            ) : (
              data?.mlflow.runs.map((r, i) => (
                <li
                  key={r.info?.run_id ?? i}
                  className="flex items-center justify-between rounded-md border border-[var(--line)] bg-white px-3 py-2"
                >
                  <span className="truncate font-mono text-xs">
                    {r.info?.run_id ?? "run"}
                  </span>
                  <span className="text-xs uppercase tracking-wide text-[var(--muted)]">
                    {r.info?.status ?? "—"}
                  </span>
                </li>
              ))
            )}
          </ul>
        </section>
      </div>
    </AppShell>
  );
}
