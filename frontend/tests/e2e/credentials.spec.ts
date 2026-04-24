// E2E credentials flow: create a bearer_token credential, see it listed,
// run its built-in ``test`` (the generic types self-report ``ok``), delete it.

import { expect, test } from "@playwright/test";

import { login, wireDiagnostics } from "./helpers/auth";

test("create, test, and delete a bearer-token credential", async ({ page }) => {
  wireDiagnostics(page);

  await login(page);
  await page.goto("/credentials");

  const name = `e2e-cred-${Date.now()}`;

  await page.getByTestId("new-credential").click();
  await expect(page.getByTestId("credential-modal")).toBeVisible();

  await page.getByTestId("cred-name").fill(name);
  await page.getByTestId("cred-type").selectOption("weftlyflow.bearer_token");
  await page.getByTestId("cred-field-token").fill("ghp_e2e_secret_token");
  await page.getByTestId("cred-save").click();

  // Row should appear in the listing.
  const row = page.locator("tr", { hasText: name });
  await expect(row).toBeVisible();
  await expect(row.locator(".mono")).toHaveText("weftlyflow.bearer_token");

  // The built-in ``test`` hook for generic types returns ok=true.
  await row.getByRole("button", { name: "Test" }).click();
  await expect(row.locator(".wf-badge.success")).toBeVisible();

  // Delete — the window.confirm dialog needs explicit accept.
  page.once("dialog", (d) => d.accept());
  await row.getByRole("button", { name: "Delete" }).click();
  await expect(page.locator("tr", { hasText: name })).toHaveCount(0);
});
