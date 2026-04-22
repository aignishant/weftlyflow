import { defineConfig, devices } from "@playwright/test";

/**
 * Golden-path E2E for the Weftlyflow editor.
 *
 * The config assumes a live backend is already running on :5678 (e.g. via
 * `make dev-api` with the Phase-2 bootstrap admin env vars set) and boots
 * the Vite dev server for the test run via `webServer`.
 */
export default defineConfig({
  testDir: "./tests/e2e",
  fullyParallel: false,
  retries: 0,
  reporter: [["list"]],
  use: {
    baseURL: "http://localhost:5173",
    trace: "on-first-retry",
    viewport: { width: 1280, height: 800 },
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
  webServer: {
    command: "npm run dev",
    url: "http://localhost:5173",
    reuseExistingServer: true,
    timeout: 120_000,
  },
});
