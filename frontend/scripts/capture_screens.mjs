// Screenshot every application screen against a running server with a seeded workspace.
// Usage: node scripts/capture_screens.mjs <base url> <out dir> <project> <model> <experiment>
//        [--theme light|dark] [--width 1440] [--height 900] [--routes a,b,c]
import { chromium } from "@playwright/test";
import { mkdirSync } from "node:fs";

const [base, out, project, model, experiment, ...rest] = process.argv.slice(2);
const opt = (k, d) => { const i = rest.indexOf(`--${k}`); return i >= 0 ? rest[i + 1] : d; };
const theme = opt("theme", "light");
const width = Number(opt("width", 1440));
const height = Number(opt("height", 900));
const ROUTES = ["projects", "import", "workbench", "features", "tolerances", "process", "virtual",
  "mechanics", "asbuilt", "hardware", "calibration", "builder", "monitor", "adaptive", "robustness",
  "sensitivity", "investigate", "worstcase", "workspace", "degradation", "fidelity", "challenge",
  "optimisation", "comparison", "external", "trust", "reports", "benchmarks", "settings"];
const routes = opt("routes", "") ? opt("routes", "").split(",") : ROUTES;
mkdirSync(out, { recursive: true });

const browser = await chromium.launch({ channel: process.env.MP_E2E_CHANNEL ?? "chrome" });
const ctx = await browser.newContext({ viewport: { width, height }, deviceScaleFactor: 1 });
await ctx.addInitScript(([p, m, e, t]) => {
  localStorage.setItem("motionproof.ui", JSON.stringify({ projectId: p, modelId: m, experimentId: e, theme: t }));
}, [project, model, experiment, theme]);
const page = await ctx.newPage();
const errors = [];
page.on("pageerror", (e) => errors.push(e.message));
for (const r of routes) {
  await page.goto(`${base}/#/${r}`);
  await page.waitForLoadState("networkidle");
  await page.waitForFunction(() => document.querySelectorAll(".loading").length === 0, null, { timeout: 30000 }).catch(() => {});
  await page.waitForTimeout(r === "workbench" || r === "virtual" ? 9000 : 600);
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  await page.screenshot({ path: `${out}/${r}.png` });
  console.log(r, overflow > 1 ? `OVERFLOW ${overflow}px` : "ok");
}
console.log("page errors:", errors.length ? errors : "none");
await browser.close();
