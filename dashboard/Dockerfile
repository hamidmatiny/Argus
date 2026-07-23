# syntax=docker/dockerfile:1
FROM node:22-bookworm AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci

FROM node:22-bookworm AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
ENV NEXT_TELEMETRY_DISABLED=1
ARG ARGUS_GATEWAY_URL=http://api-gateway:8099
ARG KEYCLOAK_ISSUER=http://localhost:8085/realms/argus
ARG NEXTAUTH_URL=http://localhost:3002
# Required at build time because next build loads auth.ts (fail-fast if unset).
# Runtime secret comes from compose/env — do not rely on this image layer value.
ARG NEXTAUTH_SECRET
ENV ARGUS_GATEWAY_URL=$ARGUS_GATEWAY_URL \
    KEYCLOAK_ISSUER=$KEYCLOAK_ISSUER \
    NEXTAUTH_URL=$NEXTAUTH_URL \
    NEXTAUTH_SECRET=$NEXTAUTH_SECRET \
    AUTH_DEMO_OFFLINE=true
RUN test -n "$NEXTAUTH_SECRET" || (echo "NEXTAUTH_SECRET build-arg is required" && exit 1)
RUN npm run build

FROM node:22-bookworm-slim AS runner
WORKDIR /app
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000 \
    HOSTNAME=0.0.0.0
RUN addgroup --system --gid 1001 nodejs && adduser --system --uid 1001 nextjs
COPY --from=builder /app/public ./public
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static
USER nextjs
EXPOSE 3000
CMD ["node", "server.js"]
