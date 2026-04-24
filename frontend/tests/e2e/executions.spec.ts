// E2E executions history: running a workflow records it in the executions
// list, and the detail view renders run-data.

import { expect, test } from "@playwright/test";

import { login, wireDiagnostics } from "./helpers/auth";

test("executing a workflow produces a row in the executions list", async ({ page }) => {
  wireDiagnostics(page);

  await login(page);

  // Create + execute a trivial workflow.
  const workflowName = `e2e-exec-${Date.now()}`;
  await page.getByTestId("workflow-name").fill(workflowName);
  await page.getByTestId("workflow-create").click();
  await expect(page).toHaveURL(/\/workflows\/wf_/);

  await page.getByTestId("palette-add-weftlyflow.set").click();
  await page.getByTestId("execute-button").click();
  await expect(page.locator(".wf-badge.success").first()).toBeVisible({
    timeout: 10_000,
  });

  // Navigate to the executions list — at least one success row must exist.
  await page.goto("/executions");
  const table = page.getByTestId("executions-table");
  await expect(table).toBeVisible();
  await expect(table.locator(".wf-badge.success").first()).toBeVisible();

  // Drill into the most recent execution's detail view.
  await table.locator("a.id").first().click();
  await expect(page).toHaveURL(/\/executions\//);
  await expect(page.getByTestId("run-data-detail")).toBeVisible();

  // Clean up the workflow.
  await page.goto("/");
  page.once("dialog", (d) => d.accept());
  await page
    .locator("tr", { hasText: workflowName })
    .getByRole("button", { name: "Delete" })
    .click();
  await expect(page.locator("tr", { hasText: workflowName })).toHaveCount(0);
});
