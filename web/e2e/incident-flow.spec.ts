import { expect, test } from "@playwright/test";

test("visitor completes a cited public investigation without a key", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Incident Assistant" })).toBeVisible();
  await expect(page.getByText("No API key required", { exact: false })).toBeVisible();
  await page.getByRole("button", { name: "Start free demo" }).click();
  await expect(page.getByRole("heading", { name: "Grounded summary" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Evidence", exact: true })).toBeVisible();
  await expect(page.getByText("Public demo result")).toBeVisible();
  await expect(page.getByRole("button", { name: "Owner key required" }).first()).toBeDisabled();
});

test("mobile workspace does not overflow horizontally", async ({ page }) => {
  await page.goto("/");
  const dimensions = await page.evaluate(() => ({
    clientWidth: document.documentElement.clientWidth,
    scrollWidth: document.documentElement.scrollWidth,
  }));
  expect(dimensions.scrollWidth).toBeLessThanOrEqual(dimensions.clientWidth);
});
