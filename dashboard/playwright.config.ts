import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  timeout: 60_000,
  use: {
    baseURL: process.env.PLAYWRIGHT_BASE_URL ?? "http://127.0.0.1:3002",
    trace: "on-first-retry",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: {
    command: "npm run start",
    url: "http://127.0.0.1:3002/login",
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
    env: {
      ...process.env,
      AUTH_DEMO_OFFLINE: "true",
      NEXTAUTH_URL: "http://127.0.0.1:3002",
      NEXTAUTH_SECRET: "playwright-secret",
      PORT: "3002",
      HOSTNAME: "127.0.0.1",
    },
  },
});
