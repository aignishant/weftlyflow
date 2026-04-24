// Shared Playwright helpers. The backend ships a bootstrap admin whose
// credentials come from WEFTLYFLOW_BOOTSTRAP_ADMIN_* env vars; the defaults
// match RUN.md so a fresh clone "just works".

import type { Page } from "@playwright/test";

export const ADMIN_EMAIL =
  process.env.WEFTLYFLOW_BOOTSTRAP_ADMIN_EMAIL ?? "admin@weftlyflow.io";
export const ADMIN_PASSWORD =
  process.env.WEFTLYFLOW_BOOTSTRAP_ADMIN_PASSWORD ?? "s3cret";

export async function login(
  page: Page,
  email: string = ADMIN_EMAIL,
  password: string = ADMIN_PASSWORD,
): Promise<void> {
  await page.goto("/login");
  await page.getByTestId("login-email").fill(email);
  await page.getByTestId("login-password").fill(password);
  await page.getByTestId("login-submit").click();
}

/** Pipe pageerror + API error responses to stdout for easier test triage. */
export function wireDiagnostics(page: Page): void {
  page.on("pageerror", (err) => console.log(`[browser exception] ${err.message}`));
  page.on("response", async (resp) => {
    const HTTP_ERROR = 400;
    if (resp.url().includes("/api/v1/") && resp.status() >= HTTP_ERROR) {
      console.log(
        `[api ${resp.status()}] ${resp.request().method()} ${resp.url()} → ${await resp.text()}`,
      );
    }
  });
}
