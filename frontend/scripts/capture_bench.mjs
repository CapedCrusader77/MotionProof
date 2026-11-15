// Capture the Benchmarks screen after running the suite from the UI.
import { chromium } from "@playwright/test";
const [base, out] = process.argv.slice(2);
const b = await chromium.launch({ channel: process.env.MP_E2E_CHANNEL ?? "chrome" });
const p = await (await b.newContext({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 1.5 })).newPage();
await p.goto(`${base}/#/benchmarks`);
await p.getByRole("button", { name: /Run all/ }).click();
await p.getByText(/NOT RUN/).first().waitFor({ timeout: 300_000 });
await p.waitForTimeout(1500);
await p.screenshot({ path: `${out}/benchmarks.png` });
await b.close();
