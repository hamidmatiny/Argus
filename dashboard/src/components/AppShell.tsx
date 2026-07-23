"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { signOut, useSession } from "next-auth/react";
import { CopilotPanel } from "@/components/CopilotPanel";

const links = [
  { href: "/", label: "Overview" },
  { href: "/incidents", label: "Incidents" },
  { href: "/data-quality", label: "Data Quality" },
  { href: "/telemetry", label: "Telemetry" },
  { href: "/pipeline", label: "Pipeline" },
];

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const { data } = useSession();
  const role = data?.user?.role ?? "viewer";

  return (
    <div className="min-h-screen grid grid-cols-[240px_1fr] bg-[var(--bg)] text-[var(--ink)]">
      <aside className="border-r border-[var(--line)] bg-[var(--panel)] px-5 py-6 flex flex-col gap-8">
        <div>
          <p className="font-display text-3xl tracking-tight leading-none">
            ARG<span className="text-[var(--accent)]">US</span>
          </p>
          <p className="mt-2 text-xs uppercase tracking-[0.18em] text-[var(--muted)]">
            Fleet operations
          </p>
        </div>
        <nav className="flex flex-col gap-1">
          {links.map((l) => {
            const active =
              l.href === "/"
                ? pathname === "/"
                : pathname.startsWith(l.href);
            return (
              <Link
                key={l.href}
                href={l.href}
                className={`rounded-md px-3 py-2 text-sm transition ${
                  active
                    ? "bg-[var(--accent-soft)] text-[var(--accent)] font-medium"
                    : "text-[var(--muted)] hover:bg-black/[0.03] hover:text-[var(--ink)]"
                }`}
              >
                {l.label}
              </Link>
            );
          })}
        </nav>
        <div className="mt-auto text-xs text-[var(--muted)] space-y-2">
          <p>
            Signed in as{" "}
            <span className="text-[var(--ink)]">{data?.user?.name ?? "—"}</span>
          </p>
          <p>
            Role{" "}
            <span className="inline-flex rounded bg-[var(--accent-soft)] px-1.5 py-0.5 text-[var(--accent)] uppercase tracking-wide">
              {role}
            </span>
          </p>
          <button
            type="button"
            onClick={() => signOut({ callbackUrl: "/login" })}
            className="underline underline-offset-2 hover:text-[var(--ink)]"
          >
            Sign out
          </button>
        </div>
      </aside>
      <main className="min-w-0 px-8 py-7">{children}</main>
      <CopilotPanel />
    </div>
  );
}
