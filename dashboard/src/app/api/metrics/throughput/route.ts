import { NextResponse } from "next/server";
import { fetchPrometheusInstant } from "@/lib/gateway";

export const dynamic = "force-dynamic";

export async function GET() {
  const eps =
    (await fetchPrometheusInstant("argus:ingestion_events_per_second")) ??
    (await fetchPrometheusInstant("sum(rate(argus_qa_records_total[1m]))")) ??
    0;
  return NextResponse.json({ eps, t: new Date().toISOString() });
}
