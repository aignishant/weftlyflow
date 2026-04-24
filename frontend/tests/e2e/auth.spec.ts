// E2E auth flows: bad-password rejection, logout returns to /login,
// protected-route redirect captures the original destination.

import { expect, test } from "@playwright/test";

import { ADMIN_EMAIL, login, wireDiagnostics } from "./helpers/auth";

test("rejects wrong password and keeps the user on /login", async ({ page }) => {
  wireDiagnostics(page);

  await login(page, ADMIN_EMAIL, "definitely-not-the-password");

  await expect(page).toHaveURL(/\/login/);
  await expect(page.getByTestId("login-error")).toBeVisible();
});

test("logout returns the user to /login", async ({ page }) => {
  wireDiagnostics(page);

  await login(page);
  await expect(page).toHaveURL(/\/$/);

  await page.getByTestId("logout").click();
  await expect(page).toHaveURL(/\/login/);
});

test("unauthenticated users are redirected with a redirect param", async ({ page }) => {
  wireDiagnostics(page);

  await page.goto("/credentials");

  await expect(page).toHaveURL(/\/login\?redirect=%2Fcredentials/);
});
