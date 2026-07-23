import { getServerSession } from "next-auth";
import { NextRequest, NextResponse } from "next/server";
import { authOptions } from "@/lib/auth";
import { getGatewayBase } from "@/lib/gateway";

async function proxy(req: NextRequest, path: string[]) {
  const session = await getServerSession(authOptions);
  if (!session) {
    return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  }
  const target = `${getGatewayBase()}/${path.join("/")}${req.nextUrl.search}`;
  const headers = new Headers();
  headers.set("Accept", "application/json");
  if (session.accessToken && !session.accessToken.startsWith("demo:")) {
    headers.set("Authorization", `Bearer ${session.accessToken}`);
  } else if (session.accessToken?.startsWith("demo:")) {
    const user = session.accessToken.slice("demo:".length);
    headers.set(
      "X-API-Key",
      user === "admin" ? "demo-admin" : user === "operator" ? "demo-operator" : "demo-viewer",
    );
  }
  const init: RequestInit = {
    method: req.method,
    headers,
    cache: "no-store",
  };
  if (req.method !== "GET" && req.method !== "HEAD") {
    init.body = await req.text();
    headers.set("Content-Type", req.headers.get("content-type") ?? "application/json");
  }
  const res = await fetch(target, init);
  const body = await res.text();
  return new NextResponse(body, {
    status: res.status,
    headers: { "Content-Type": res.headers.get("content-type") ?? "application/json" },
  });
}

export async function GET(
  req: NextRequest,
  ctx: { params: Promise<{ path: string[] }> },
) {
  const { path } = await ctx.params;
  return proxy(req, path);
}

export async function POST(
  req: NextRequest,
  ctx: { params: Promise<{ path: string[] }> },
) {
  const { path } = await ctx.params;
  return proxy(req, path);
}
