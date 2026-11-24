import { defineConfig, devices } from "@playwright/test";
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

// The E2E suite runs the real backend (FastAPI + MuJoCo) serving the built frontend from
// frontend/dist, against a fresh, empty workspace. Build first: `npm run build`.
const PORT = Number(process.env.MP_E2E_PORT ?? 8765);
const HOME = process.env.MP_E2E_HOME ?? mkdtempSync(join(tmpdir(), "mp-e2e-"));
const PYTHON = process.env.MP_PYTHON ?? (process.platform === "win32"
  ? "..\\.venv\\Scripts\\python.exe" : "../.venv/bin/python");

export default defineConfig({
  testDir: "./e2e",
  timeout: 120_000,
  expect: { timeout: 20_000 },
  fullyParallel: false,
  workers: 1,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [["list"], ["html", { open: "never" }]] : "list",
  use: {
    baseURL: `http://127.0.0.1:${PORT}`,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  // CI installs the bundled Chromium; locally MP_E2E_CHANNEL=chrome (or msedge) uses an installed
  // browser instead of downloading one.
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"],
    ...(process.env.MP_E2E_CHANNEL ? { channel: process.env.MP_E2E_CHANNEL } : {}) } }],
  webServer: {
    command: `"${PYTHON}" -m motionproof.cli.main serve --require-sign-in --port ${PORT} --home "${HOME}"`,
    url: `http://127.0.0.1:${PORT}/api/v1/health`,
    timeout: 120_000,
    reuseExistingServer: false,
    stdout: "ignore",
    stderr: "pipe",
  },
});
