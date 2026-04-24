// One-shot screenshot capture for the README. Requires the dev stack to be
// running (frontend on :5173, api on :5678) and the bootstrap admin
// (`admin@weftlyflow.io` / `s3cret`) seeded.
//
// Usage:
//   node scripts/capture_screenshots.mjs
//
// Outputs: docs/images/dashboard.png, docs/images/workflow-editor.png

import { chromium } from "@playwright/test";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";
import { mkdirSync } from "node:fs";

const __dirname = dirname(fileURLToPath(import.meta.url));
const OUT_DIR = resolve(__dirname, "..", "..", "docs", "images");
mkdirSync(OUT_DIR, { recursive: true });

const FRONTEND = "http://localhost:5173";
const EMAIL = "admin@weftlyflow.io";
const PASSWORD = "s3cret";

const VIEWPORT = { width: 1440, height: 900 };

const browser = await chromium.launch();
const ctx = await browser.newContext({ viewport: VIEWPORT, deviceScaleFactor: 2 });

// Mark all onboarding tours as already-seen so the overlay never auto-plays.
await ctx.addInitScript(() => {
  const ids = ["home.v2", "editor.v2", "credentials.v1", "executions.v1"];
  for (const id of ids) {
    try {
      window.localStorage.setItem(`weftlyflow.tour.seen.${id}`, "1");
    } catch {
      /* ignore */
    }
  }
});

const page = await ctx.newPage();

console.log("→ logging in");
await page.goto(`${FRONTEND}/login`, { waitUntil: "domcontentloaded" });
await page.fill('input[type="email"]', EMAIL);
await page.fill('input[type="password"]', PASSWORD);
await Promise.all([
  page.waitForURL((u) => !u.pathname.startsWith("/login"), { timeout: 15_000 }),
  page.click('button[type="submit"]'),
]);

console.log("→ dashboard");
await page.goto(`${FRONTEND}/`, { waitUntil: "networkidle" });
await page.waitForTimeout(1200);
await page.screenshot({
  path: resolve(OUT_DIR, "dashboard.png"),
  fullPage: true,
});

console.log("→ workflow editor");
// Pull a workflow id from the API and deep-link the editor — the dashboard
// has no row-level test hook, and the form-driven create flow loses races.
const wfList = await page.evaluate(async () => {
  const token = window.localStorage.getItem("weftlyflow.access_token");
  const r = await fetch("/api/v1/workflows", {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  return r.ok ? r.json() : { error: r.status };
});
const workflowId = wfList?.items?.[0]?.id ?? wfList?.[0]?.id;
if (!workflowId) {
  throw new Error(`No workflow available; create one first. Got: ${JSON.stringify(wfList)}`);
}
await page.goto(`${FRONTEND}/workflows/${workflowId}`, { waitUntil: "networkidle" });
await page.waitForTimeout(2000);
await page.screenshot({
  path: resolve(OUT_DIR, "workflow-editor.png"),
  fullPage: false, // canvas is fixed-viewport — fullPage just shows blank
});

await browser.close();
console.log(`done → ${OUT_DIR}`);
