// Capture README screenshots from a running MotionProof server with a seeded workspace.
// Usage: node scripts/capture_media.mjs <base url> <out dir> <project> <model> <experiment>
import { chromium } from "@playwright/test";
import { mkdirSync } from "node:fs";

const [base, out, project, model, experiment] = process.argv.slice(2);
mkdirSync(out, { recursive: true });
mkdirSync(`${out}/frames`, { recursive: true });

const browser = await chromium.launch({ channel: process.env.MP_E2E_CHANNEL ?? "chrome" });
const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 1.5 });
await ctx.addInitScript(([p, m, e, theme]) => {
  localStorage.setItem("motionproof.ui", JSON.stringify({ projectId: p, modelId: m, experimentId: e, theme }));
}, [project, model, experiment, process.env.MP_THEME ?? "light"]);
const page = await ctx.newPage();

async function shot(route, name, settle = 2500, prep) {
  await page.goto(`${base}/#/${route}`);
  await page.waitForLoadState("networkidle");
  await page.waitForTimeout(settle);
  if (prep) await prep();
  await page.screenshot({ path: `${out}/${name}.png` });
  console.log("captured", name);
}

const routes = process.argv.slice(7).length ? process.argv.slice(7) : [
  "projects", "workbench", "tolerances", "virtual", "mechanics", "robustness", "sensitivity",
  "worstcase", "asbuilt", "process", "hardware", "challenge", "workspace", "trust", "benchmarks"];
for (const r of routes) {
  if (r === "workbench") {
    await shot(r, r, 6000, async () => {
      await page.getByRole("button", { name: "Fit" }).click().catch(() => {});
      await page.waitForTimeout(2000);
    });
  } else await shot(r, r);
}

// GIF frames: a short tour of the workflow
let i = 0;
for (const r of ["projects", "workbench", "tolerances", "virtual", "robustness", "sensitivity", "trust", "benchmarks"]) {
  await page.goto(`${base}/#/${r}`);
  await page.waitForLoadState("networkidle");
  await page.waitForTimeout(2000);
  await page.screenshot({ path: `${out}/frames/${String(i++).padStart(2, "0")}_${r}.png` });
}

// GIF frames: orbit the assembly in the workbench viewport
{
  const p = await (await browser.newContext({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 1 })).newPage();
  await p.addInitScript(([pr, m, e]) => {
    localStorage.setItem("motionproof.ui", JSON.stringify({ projectId: pr, modelId: m, experimentId: e, theme: "light", navCollapsed: true }));
  }, [project, model, experiment]);
  await p.goto(`${base}/#/workbench`);
  await p.waitForLoadState("networkidle");
  await p.waitForTimeout(6000);
  await p.getByRole("button", { name: "Fit" }).click().catch(() => {});
  await p.waitForTimeout(1500);
  const canvas = p.locator("canvas").first();
  const box = await canvas.boundingBox();
  mkdirSync(`${out}/orbit`, { recursive: true });
  const cx = box.x + box.width / 2, cy = box.y + box.height / 2;
  for (let k = 0; k < 36; k++) {
    await p.mouse.move(cx, cy);
    await p.mouse.down();
    await p.mouse.move(cx + 18, cy, { steps: 3 });
    await p.mouse.up();
    await p.waitForTimeout(120);
    await canvas.screenshot({ path: `${out}/orbit/${String(k).padStart(2, "0")}.png` });
  }
}
await browser.close();
