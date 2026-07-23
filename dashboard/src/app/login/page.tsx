"use client";

import { signIn } from "next-auth/react";
import { useRouter, useSearchParams } from "next/navigation";
import { FormEvent, Suspense, useState } from "react";

function LoginForm() {
  const router = useRouter();
  const params = useSearchParams();
  const [username, setUsername] = useState("operator");
  const [password, setPassword] = useState("operator");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    const res = await signIn("demo", {
      username,
      password,
      redirect: false,
    });
    setBusy(false);
    if (res?.error) {
      setError("Login failed — check Keycloak or enable AUTH_DEMO_OFFLINE=true");
      return;
    }
    router.push(params.get("callbackUrl") || "/");
    router.refresh();
  }

  return (
    <div className="flex min-h-screen items-center justify-center px-4">
      <div className="w-full max-w-md rounded-2xl border border-[var(--line)] bg-[var(--panel)] p-8 shadow-sm">
        <p className="font-display text-4xl tracking-tight">
          ARG<span className="text-[var(--accent)]">US</span>
        </p>
        <p className="mt-2 text-sm text-[var(--muted)]">
          Sign in with Keycloak (realm <code>argus</code>) or demo credentials.
        </p>

        <form onSubmit={onSubmit} className="mt-8 space-y-4">
          <label className="block text-sm" htmlFor="username">
            <span className="text-[var(--muted)]">Username</span>
            <input
              id="username"
              className="mt-1 w-full rounded-md border border-[var(--line)] bg-white px-3 py-2"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              autoComplete="username"
            />
          </label>
          <label className="block text-sm" htmlFor="password">
            <span className="text-[var(--muted)]">Password</span>
            <input
              id="password"
              type="password"
              className="mt-1 w-full rounded-md border border-[var(--line)] bg-white px-3 py-2"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete="current-password"
            />
          </label>
          {error ? <p className="text-sm text-red-700">{error}</p> : null}
          <button
            type="submit"
            disabled={busy}
            className="w-full rounded-md bg-[var(--accent)] py-2.5 text-sm font-medium text-white disabled:opacity-60"
          >
            {busy ? "Signing in…" : "Sign in"}
          </button>
        </form>

        <button
          type="button"
          className="mt-3 w-full rounded-md border border-[var(--line)] py-2.5 text-sm"
          onClick={() => signIn("keycloak", { callbackUrl: "/" })}
        >
          Continue with Keycloak OIDC
        </button>

        <p className="mt-6 text-xs text-[var(--muted)]">
          Demo users: viewer/viewer · operator/operator · admin/admin
        </p>
      </div>
    </div>
  );
}

export default function LoginPage() {
  return (
    <Suspense>
      <LoginForm />
    </Suspense>
  );
}
