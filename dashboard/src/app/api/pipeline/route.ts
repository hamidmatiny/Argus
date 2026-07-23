import { getServerSession } from "next-auth";
import { NextResponse } from "next/server";
import { authOptions } from "@/lib/auth";

export const dynamic = "force-dynamic";

type DagsterRun = { id: string; status: string; jobName?: string };
type MLflowRun = { info?: { run_id?: string; status?: string; experiment_id?: string } };

export async function GET() {
  const session = await getServerSession(authOptions);
  if (!session) {
    return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  }

  const dagsterURL =
    process.env.DAGSTER_GRAPHQL_URL ?? "http://localhost:3000/graphql";
  const mlflowURL =
    process.env.MLFLOW_TRACKING_URI ?? "http://localhost:5002";

  let dagster: { runs: DagsterRun[]; error?: string } = { runs: [] };
  try {
    const query = `{
      runsOrError(limit: 8) {
        __typename
        ... on Runs { results { runId status jobName } }
        ... on PythonError { message }
      }
    }`;
    const res = await fetch(dagsterURL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query }),
      cache: "no-store",
    });
    const json = (await res.json()) as {
      data?: {
        runsOrError?: {
          __typename?: string;
          results?: { runId: string; status: string; jobName?: string }[];
          message?: string;
        };
      };
      errors?: { message: string }[];
    };
    if (json.errors?.length) {
      dagster = { runs: [], error: json.errors[0].message };
    } else if (json.data?.runsOrError?.results) {
      dagster = {
        runs: json.data.runsOrError.results.map((r) => ({
          id: r.runId,
          status: r.status,
          jobName: r.jobName,
        })),
      };
    } else if (json.data?.runsOrError?.message) {
      dagster = { runs: [], error: json.data.runsOrError.message };
    }
  } catch (err) {
    dagster = {
      runs: [],
      error: err instanceof Error ? err.message : "dagster unreachable",
    };
  }

  let mlflow: { runs: MLflowRun[]; error?: string } = { runs: [] };
  try {
    const res = await fetch(`${mlflowURL.replace(/\/$/, "")}/api/2.0/mlflow/runs/search`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ max_results: 8 }),
      cache: "no-store",
    });
    if (!res.ok) {
      mlflow = { runs: [], error: `mlflow ${res.status}` };
    } else {
      const json = (await res.json()) as { runs?: MLflowRun[] };
      mlflow = { runs: json.runs ?? [] };
    }
  } catch (err) {
    mlflow = {
      runs: [],
      error: err instanceof Error ? err.message : "mlflow unreachable",
    };
  }

  return NextResponse.json({ dagster, mlflow });
}
