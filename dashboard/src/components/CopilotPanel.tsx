"use client";

import { FormEvent, useState } from "react";

type AskResponse = {
  answer: string;
  citations?: string[];
  tool_calls?: { tool: string }[];
};

/**
 * "Ask the fleet" — read-only copilot chat via gateway POST /v1/copilot/ask.
 */
export function CopilotPanel() {
  const [open, setOpen] = useState(false);
  const [question, setQuestion] = useState(
    "why did vehicle VH-0003 trip its breaker at 14:02?",
  );
  const [answer, setAnswer] = useState<string | null>(null);
  const [meta, setMeta] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    setAnswer(null);
    try {
      const res = await fetch("/api/gateway/v1/copilot/ask", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question }),
      });
      const body = await res.json().catch(() => ({}));
      if (!res.ok) {
        throw new Error(
          body?.detail?.reason || body?.error || body?.detail || res.statusText,
        );
      }
      const data = body as AskResponse;
      setAnswer(data.answer);
      const tools = (data.tool_calls || []).map((t) => t.tool).join(", ");
      const cites = (data.citations || []).join(", ");
      setMeta([tools && `tools: ${tools}`, cites && `cites: ${cites}`]
        .filter(Boolean)
        .join(" · "));
    } catch (err) {
      setError(err instanceof Error ? err.message : "ask failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="fixed bottom-5 right-5 z-40 flex flex-col items-end gap-2">
      {open ? (
        <div className="w-[min(420px,calc(100vw-2rem))] rounded-2xl border border-[var(--line)] bg-[var(--panel)] shadow-lg">
          <div className="flex items-center justify-between border-b border-[var(--line)] px-4 py-3">
            <div>
              <p className="font-display text-lg leading-none">Ask the fleet</p>
              <p className="mt-1 text-xs text-[var(--muted)]">
                Read-only copilot — cannot ack, resolve, or retrain
              </p>
            </div>
            <button
              type="button"
              className="text-sm text-[var(--muted)] hover:text-[var(--ink)]"
              onClick={() => setOpen(false)}
            >
              Close
            </button>
          </div>
          <form onSubmit={onSubmit} className="space-y-3 p-4">
            <textarea
              className="min-h-[88px] w-full rounded-md border border-[var(--line)] bg-white px-3 py-2 text-sm"
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              aria-label="Copilot question"
            />
            <button
              type="submit"
              disabled={busy}
              className="w-full rounded-md bg-[var(--accent)] py-2 text-sm font-medium text-white disabled:opacity-60"
            >
              {busy ? "Thinking…" : "Ask"}
            </button>
            {error ? <p className="text-sm text-red-700">{error}</p> : null}
            {answer ? (
              <div className="rounded-md bg-[var(--accent-soft)]/40 p-3 text-sm leading-relaxed">
                {answer}
              </div>
            ) : null}
            {meta ? (
              <p className="text-xs text-[var(--muted)]">{meta}</p>
            ) : null}
          </form>
        </div>
      ) : null}
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="rounded-full bg-[var(--accent)] px-4 py-2.5 text-sm font-medium text-white shadow-md"
      >
        Ask the fleet
      </button>
    </div>
  );
}
