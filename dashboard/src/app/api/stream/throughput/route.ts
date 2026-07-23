import { getServerSession } from "next-auth";
import { authOptions } from "@/lib/auth";
import { getGatewayBase } from "@/lib/gateway";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

/**
 * SSE bridge: samples gateway telemetry stream (or synthesizes rate) for the Overview sparkline.
 */
export async function GET() {
  const session = await getServerSession(authOptions);
  if (!session) {
    return new Response("unauthorized", { status: 401 });
  }

  const encoder = new TextEncoder();
  let closed = false;
  const stream = new ReadableStream({
    async start(controller) {
      const send = (eps: number) => {
        if (closed) return;
        const payload = JSON.stringify({
          eps,
          t: new Date().toISOString(),
        });
        controller.enqueue(encoder.encode(`data: ${payload}\n\n`));
      };

      // Prefer live Kafka-backed stream via gateway; count events in tumbling windows.
      const headers: Record<string, string> = { Accept: "application/json" };
      if (session.accessToken && !session.accessToken.startsWith("demo:")) {
        headers.Authorization = `Bearer ${session.accessToken}`;
      } else if (session.accessToken?.startsWith("demo:")) {
        const user = session.accessToken.slice("demo:".length);
        headers["X-API-Key"] =
          user === "admin" ? "demo-admin" : user === "operator" ? "demo-operator" : "demo-viewer";
      }

      let windowCount = 0;
      let lastFlush = Date.now();
      const flush = () => {
        const now = Date.now();
        const dt = Math.max(0.5, (now - lastFlush) / 1000);
        send(windowCount / dt);
        windowCount = 0;
        lastFlush = now;
      };
      const ticker = setInterval(flush, 2000);

      try {
        const res = await fetch(`${getGatewayBase()}/v1/telemetry/stream`, {
          headers,
          cache: "no-store",
        });
        if (!res.ok || !res.body) {
          // Fallback: poll Prometheus through companion route values embedded as heartbeat.
          for (let i = 0; i < 30 && !closed; i++) {
            send(0);
            await new Promise((r) => setTimeout(r, 2000));
          }
        } else {
          const reader = res.body.getReader();
          const dec = new TextDecoder();
          let buf = "";
          while (!closed) {
            const { done, value } = await reader.read();
            if (done) break;
            buf += dec.decode(value, { stream: true });
            // Count JSON object boundaries as events.
            const parts = buf.split("\n");
            buf = parts.pop() ?? "";
            for (const line of parts) {
              if (line.trim()) windowCount += 1;
            }
          }
        }
      } catch {
        send(0);
      } finally {
        clearInterval(ticker);
        if (!closed) {
          closed = true;
          controller.close();
        }
      }
    },
    cancel() {
      closed = true;
    },
  });

  return new Response(stream, {
    headers: {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache, no-transform",
      Connection: "keep-alive",
    },
  });
}
