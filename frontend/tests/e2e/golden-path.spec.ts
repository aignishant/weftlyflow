// Bible-mandated golden path:
//   1. Log in.
//   2. Create a workflow (Manual Trigger → HTTP Request → Set).
//   3. Execute it, assert status = success.
//   4. Delete the workflow.
//
// Runs against a live backend at :5678. The test server ships a bootstrap
// admin account whose credentials come from WEFTLYFLOW_BOOTSTRAP_ADMIN_*
// env vars. Defaults below match the ones in RUN.md so the block "just
// works" in a fresh clone.

import { expect, test } from "@playwright/test";

const ADMIN_EMAIL = process.env.WEFTLYFLOW_BOOTSTRAP_ADMIN_EMAIL ?? "admin@weftlyflow.io";
const ADMIN_PASSWORD = process.env.WEFTLYFLOW_BOOTSTRAP_ADMIN_PASSWORD ?? "s3cret";

test("create, execute, delete a workflow", async ({ page }) => {
  // Surface unexpected client-side errors + failed API calls so a regression
  // reports the underlying cause instead of the downstream URL assertion.
  page.on("pageerror", (err) => console.log(`[browser exception] ${err.message}`));
  page.on("response", async (resp) => {
    const HTTP_ERROR = 400;
    if (resp.url().includes("/api/v1/") && resp.status() >= HTTP_ERROR) {
      console.log(
        `[api ${resp.status()}] ${resp.request().method()} ${resp.url()} → ${await resp.text()}`,
      );
    }
  });

  await page.goto("/login");

  await page.getByTestId("login-email").fill(ADMIN_EMAIL);
  await page.getByTestId("login-password").fill(ADMIN_PASSWORD);
  await page.getByTestId("login-submit").click();

  await expect(page).toHaveURL(/\/$/);

  const workflowName = `e2e-${Date.now()}`;
  await page.getByTestId("workflow-name").fill(workflowName);
  await page.getByTestId("workflow-create").click();

  // Navigated into the editor.
  await expect(page).toHaveURL(/\/workflows\/wf_/);
  await expect(page.getByTestId("editor-name")).toHaveValue(workflowName);

  // Add a Set node from the palette.
  await page.getByTestId("palette-add-weftlyflow.set").click();

  // Execute — the panel should flip to success.
  await page.getByTestId("execute-button").click();
  await expect(page.locator('[data-testid="run-data"]')).toBeVisible();
  await expect(page.locator(".wf-badge.success").first()).toBeVisible({
    timeout: 10_000,
  });

  // Back to the list + delete to keep the DB clean.
  await page.getByTestId("editor-back").click();
  await expect(page).toHaveURL(/\/$/);
  page.once("dialog", (d) => d.accept());
  await page
    .locator("tr", { hasText: workflowName })
    .getByRole("button", { name: "Delete" })
    .click();
  await expect(page.locator("tr", { hasText: workflowName })).toHaveCount(0);
});
