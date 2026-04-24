// Bible-mandated golden path:
//   1. Log in.
//   2. Create a workflow (Manual Trigger → Set).
//   3. Execute it, assert status = success.
//   4. Delete the workflow.
//
// Runs against a live backend at :5678.

import { expect, test } from "@playwright/test";

import { login, wireDiagnostics } from "./helpers/auth";

test("create, execute, delete a workflow", async ({ page }) => {
  wireDiagnostics(page);

  await login(page);
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
