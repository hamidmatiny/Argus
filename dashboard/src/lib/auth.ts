import type { NextAuthOptions } from "next-auth";
import KeycloakProvider from "next-auth/providers/keycloak";
import CredentialsProvider from "next-auth/providers/credentials";
import { normalizeRole } from "@/lib/types";

const issuer =
  process.env.KEYCLOAK_ISSUER ?? "http://localhost:8085/realms/argus";
const clientId = process.env.KEYCLOAK_CLIENT_ID ?? "argus-dashboard";
// Demo Keycloak client secret — intentional fallback. Same value is public in
// api-gateway/keycloak/argus-realm.json (local non-prod realm import).
const clientSecret =
  process.env.KEYCLOAK_CLIENT_SECRET ?? "argus-dashboard-secret";

const nextAuthSecret = process.env.NEXTAUTH_SECRET;
if (!nextAuthSecret) {
  throw new Error(
    "NEXTAUTH_SECRET is required. Generate one with `openssl rand -base64 32` and set it in dashboard/.env.local."
  );
}

function rolesFromToken(payload: Record<string, unknown>): string[] {
  const roles: string[] = [];
  const realm = payload.realm_access as { roles?: string[] } | undefined;
  if (realm?.roles) roles.push(...realm.roles);
  const resource = payload.resource_access as
    | Record<string, { roles?: string[] }>
    | undefined;
  if (resource) {
    for (const v of Object.values(resource)) {
      if (v?.roles) roles.push(...v.roles);
    }
  }
  if (Array.isArray(payload.roles)) {
    roles.push(...(payload.roles as string[]));
  }
  return roles;
}

function decodeJwt(token: string): Record<string, unknown> {
  try {
    const part = token.split(".")[1];
    if (!part) return {};
    const json = Buffer.from(part, "base64url").toString("utf8");
    return JSON.parse(json) as Record<string, unknown>;
  } catch {
    return {};
  }
}

export const authOptions: NextAuthOptions = {
  providers: [
    KeycloakProvider({
      clientId,
      clientSecret,
      issuer,
    }),
    CredentialsProvider({
      id: "demo",
      name: "Demo login",
      credentials: {
        username: { label: "Username", type: "text" },
        password: { label: "Password", type: "password" },
      },
      async authorize(credentials) {
        const username = credentials?.username?.trim();
        const password = credentials?.password ?? "";
        if (!username) return null;

        // Prefer live Keycloak password grant when reachable.
        try {
          const body = new URLSearchParams({
            client_id: "argus-gateway",
            username,
            password,
            grant_type: "password",
          });
          const res = await fetch(`${issuer}/protocol/openid-connect/token`, {
            method: "POST",
            headers: { "Content-Type": "application/x-www-form-urlencoded" },
            body,
          });
          if (res.ok) {
            const data = (await res.json()) as { access_token: string };
            const claims = decodeJwt(data.access_token);
            const roles = rolesFromToken(claims);
            return {
              id: String(claims.sub ?? username),
              name: username,
              email: String(claims.email ?? `${username}@argus.local`),
              accessToken: data.access_token,
              roles,
            } as { id: string; name: string; email: string; accessToken: string; roles: string[] };
          }
        } catch {
          // fall through to offline demo roles
        }

        if (process.env.AUTH_DEMO_OFFLINE === "true") {
          const roleMap: Record<string, string[]> = {
            viewer: ["viewer"],
            operator: ["operator", "viewer"],
            admin: ["admin", "operator", "viewer"],
          };
          const roles = roleMap[username] ?? ["viewer"];
          return {
            id: username,
            name: username,
            email: `${username}@argus.local`,
            accessToken: `demo:${username}`,
            roles,
          } as { id: string; name: string; email: string; accessToken: string; roles: string[] };
        }
        return null;
      },
    }),
  ],
  callbacks: {
    async jwt({ token, account, user }) {
      if (account?.access_token) {
        token.accessToken = account.access_token;
        const claims = decodeJwt(account.access_token);
        token.roles = rolesFromToken(claims);
        token.role = normalizeRole(token.roles);
      }
      if (user && "accessToken" in user) {
        const u = user as { accessToken?: string; roles?: string[] };
        if (u.accessToken) token.accessToken = u.accessToken;
        if (u.roles) {
          token.roles = u.roles;
          token.role = normalizeRole(u.roles);
        }
      }
      return token;
    },
    async session({ session, token }) {
      session.accessToken = token.accessToken;
      session.roles = token.roles;
      if (session.user) {
        session.user.role = token.role as string | undefined;
      }
      return session;
    },
  },
  pages: {
    signIn: "/login",
  },
  secret: nextAuthSecret,
};
