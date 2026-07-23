"use client";

import { useEffect, useMemo, useState } from "react";
import { TimeSeriesChart } from "@/components/TimeSeriesChart";

type Point = { t: string; v: number };

/**
 * Live throughput sparkline. Prefers SSE from /api/stream/throughput
 * (gateway telemetry stream → event rate); falls back to Prometheus poll.
 */
export function LiveThroughput() {
  const [points, setPoints] = useState<Point[]>([]);
  const [source, setSource] = useState<"stream" | "prom" | "idle">("idle");
  const [eps, setEps] = useState(0);

  useEffect(() => {
    const es = new EventSource("/api/stream/throughput");
    es.onmessage = (ev) => {
      try {
        const data = JSON.parse(ev.data) as { eps: number; t: string };
        setSource("stream");
        setEps(data.eps);
        setPoints((prev) => {
          const next = [...prev, { t: data.t.slice(11, 19), v: data.eps }];
          return next.slice(-40);
        });
      } catch {
        /* ignore */
      }
    };
    es.onerror = () => {
      es.close();
      setSource("prom");
    };
    return () => es.close();
  }, []);

  useEffect(() => {
    if (source === "stream") return;
    let cancelled = false;
    async function poll() {
      try {
        const res = await fetch("/api/metrics/throughput", { cache: "no-store" });
        if (!res.ok) return;
        const data = (await res.json()) as { eps: number; t: string };
        if (cancelled) return;
        setEps(data.eps);
        setPoints((prev) => {
          const next = [...prev, { t: data.t.slice(11, 19), v: data.eps }];
          return next.slice(-40);
        });
      } catch {
        /* ignore */
      }
    }
    poll();
    const id = setInterval(poll, 2000);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, [source]);

  const label = useMemo(() => {
    if (source === "stream") return "live stream";
    if (source === "prom") return "prometheus";
    return "connecting…";
  }, [source]);

  return (
    <section className="rounded-xl border border-[var(--line)] bg-[var(--panel)] p-5 shadow-[0_1px_0_rgba(26,40,48,0.04)]">
      <div className="flex items-end justify-between gap-4">
        <div>
          <h2 className="font-display text-xl">Ingestion throughput</h2>
          <p className="text-sm text-[var(--muted)]">Events / sec · {label}</p>
        </div>
        <p className="font-display text-3xl tabular-nums text-[var(--accent)]">
          {eps.toFixed(1)}
          <span className="ml-1 text-sm text-[var(--muted)]">eps</span>
        </p>
      </div>
      <div className="mt-4">
        <TimeSeriesChart data={points.length ? points : [{ t: "—", v: 0 }]} />
      </div>
    </section>
  );
}
