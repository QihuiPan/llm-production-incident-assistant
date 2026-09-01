import { expect, test } from "@playwright/test";

test("operator completes a cited read-only investigation", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Incident Assistant" })).toBeVisible();
  await page.getByRole("button", { name: "Start investigation" }).click();
  await expect(page.getByRole("heading", { name: "Grounded summary" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Evidence", exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Runtime dashboard" })).toBeVisible();

  const approval = page.getByRole("button", { name: "Approve and run" }).first();
  await approval.click();
  await expect(page.getByRole("button", { name: "Executed" }).first()).toBeDisabled();

  await page.getByRole("button", { name: "Record positive review" }).click();
  await expect(page.getByRole("button", { name: "Feedback recorded" })).toBeDisabled();
});

test("mobile workspace does not overflow horizontally", async ({ page }) => {
  await page.goto("/");
  const dimensions = await page.evaluate(() => ({
    clientWidth: document.documentElement.clientWidth,
    scrollWidth: document.documentElement.scrollWidth,
  }));
  expect(dimensions.scrollWidth).toBeLessThanOrEqual(dimensions.clientWidth);
});
