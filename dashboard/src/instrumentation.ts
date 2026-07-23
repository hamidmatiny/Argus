/**
 * Fail fast on boot if required secrets are missing (loads auth.ts checks).
 * Next.js only evaluates route modules on first request otherwise.
 */
export async function register() {
  if (process.env.NEXT_RUNTIME === "nodejs") {
    await import("@/lib/auth");
  }
}
