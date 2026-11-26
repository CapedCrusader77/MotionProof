// Captures the product screens used by the README and the homepage from a running MotionProof
// server (1600 x 1000). It needs an account that owns the workspace with the reference data, which
// is the FIRST account registered on that server, so run it against a COPY of a workspace:
//
//   uv run motionproof serve --home <copy of workspace> --port 8790
//   MP_EMAIL=you@lab.org MP_PASSWORD=... node tools/capture-screens.mjs http://127.0.0.1:8790 <folder> [dark|light]
//
// Without MP_EMAIL it registers a throw-away account (which owns the workspace only if it is the
// first account on the server).

// The workspace needs project PRJ_001 with model MDL_001 and experiment EXP_001 (the reference
// design and its 1000-scenario reversal run).
import { chromium } from "@playwright/test";

const [base = "http://127.0.0.1:8790", out = ".", theme = "dark"] = process.argv.slice(2);
const SCREENS = ["projects", "workbench", "tolerances", "virtual", "mechanics", "hardware", "robustness", "sensitivity", "trust", "benchmarks"];

for (let i = 0; i < 60; i++) {
  try { if ((await fetch(`${base}/api/v1/health`)).ok) break; } catch { /* server still starting */ }
  await new Promise((r) => setTimeout(r, 1000));
}
const browser = await chromium.launch({ channel: process.env.MP_E2E_CHANNEL });
const ctx = await browser.newContext({ viewport: { width: 1600, height: 1000 } });
const email = process.env.MP_EMAIL ?? `shots${Date.now()}@lab.org`;
const password = process.env.MP_PASSWORD ?? `shots-${Math.random().toString(36).slice(2)}`;
const res = await ctx.request.post(`${base}/api/v1/auth/${process.env.MP_EMAIL ? "login" : "register"}`, { data: { email, password } });
if (!res.ok()) throw new Error(`could not sign in to capture (${res.status()})`);
const page = await ctx.newPage();
await page.addInitScript(([t, e]) => localStorage.setItem("motionproof.ui", JSON.stringify({
  projectId: "PRJ_001", modelId: "MDL_001", experimentId: "EXP_001", theme: t, user: e })), [theme, email]);
for (const key of SCREENS) {
  await page.goto(`${base}/#/${key}`);
  if (key === "workbench") await page.waitForResponse((r) => r.url().includes("/meshes/"), { timeout: 120000 }).catch(() => undefined);
  await page.waitForFunction(() => !/Loading|Analysing/.test(document.body.innerText), null, { timeout: 300000 }).catch(() => console.log("still loading:", key));
  await page.waitForTimeout(key === "workbench" ? 8000 : 2500);
  await page.screenshot({ path: `${out}/${key}.png` });
  console.log("captured", key);
}
await browser.close();
