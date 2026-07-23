import { expect, test } from "@playwright/test";

test("overview renders after demo login", async ({ page }) => {
  await page.goto("/login");
  await page.getByLabel("Username").fill("operator");
  await page.getByLabel("Password").fill("operator");
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.waitForURL("/");
  await expect(page.getByRole("heading", { name: "Overview" })).toBeVisible();
  await expect(page.getByTestId("stat-open-incidents")).toBeVisible();
  await expect(page.getByText("Ingestion throughput")).toBeVisible();
});
