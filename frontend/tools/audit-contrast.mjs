// Text-contrast audit of the app in both themes, against a running server (WCAG AA: 4.5:1, or
// 3:1 for large text). For every visible text node on the listed screens it composites the text
// colour over the real background and reports anything below the threshold. Exit code 1 if any.
//
//   MP_EMAIL=you@lab.org MP_PASSWORD=... node tools/audit-contrast.mjs http://127.0.0.1:8790
//
// Use the account that owns the reference workspace (see capture-screens.mjs), otherwise the
// screens show empty states and little is checked.
import { chromium } from "@playwright/test";

const base = process.argv[2] ?? "http://127.0.0.1:8790";
const SCREENS = ["projects", "workbench", "tolerances", "mechanics", "hardware", "robustness", "sensitivity", "trust", "benchmarks", "settings"];
if (!process.env.MP_EMAIL) throw new Error("set MP_EMAIL and MP_PASSWORD");

const browser = await chromium.launch({ channel: process.env.MP_E2E_CHANNEL });
const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
const login = await ctx.request.post(`${base}/api/v1/auth/login`, { data: { email: process.env.MP_EMAIL, password: process.env.MP_PASSWORD } });
if (!login.ok()) throw new Error(`sign-in failed (${login.status()})`);

const audit = (page) => page.evaluate(() => {
  // computed colours come as rgb()/rgba(), or color(srgb r g b / a) for color-mix() results
  const parse = (c) => {
    const srgb = c.match(/color\(srgb ([^)]+)\)/);
    if (srgb) { const [r, g, b, a = 1] = srgb[1].split(/[ /]+/).filter(Boolean).map(Number); return { r: r * 255, g: g * 255, b: b * 255, a }; }
    const m = c.match(/rgba?\(([^)]+)\)/);
    if (!m) throw new Error(`unsupported colour ${c}`);
    const [r, g, b, a = 1] = m[1].split(/[ ,/]+/).filter(Boolean).map(Number);
    return { r, g, b, a };
  };
  const lum = ({ r, g, b }) => { const f = (c) => { c /= 255; return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4; }; return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b); };
  const over = (t, bo) => ({ r: t.r * t.a + bo.r * (1 - t.a), g: t.g * t.a + bo.g * (1 - t.a), b: t.b * t.a + bo.b * (1 - t.a), a: 1 });
  const bgOf = (el) => {
    const stack = [];
    for (let e = el; e; e = e.parentElement) {
      const cs = getComputedStyle(e);
      // dark panels paint a gradient; use its mid colour
      if (cs.backgroundImage.includes("gradient") && e.matches(".panel")) { stack.push({ r: 21, g: 21, b: 21, a: 1 }); break; }
      const c = parse(cs.backgroundColor);
      if (c.a > 0) { stack.push(c); if (c.a === 1) break; }
    }
    let acc = { r: 255, g: 255, b: 255, a: 1 };
    for (const c of stack.reverse()) acc = over(c, acc);
    return acc;
  };
  const out = [];
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  for (let n; (n = walker.nextNode());) {
    const text = n.textContent.trim();
    const el = n.parentElement;
    if (!text || !el || el.closest("canvas,svg,script,style,.skip-link")) continue;
    if (el.getBoundingClientRect().width < 2) continue;
    const cs = getComputedStyle(el);
    if (cs.visibility === "hidden" || cs.display === "none" || +cs.opacity === 0) continue;
    const bg = bgOf(el), fg = over(parse(cs.color), bg);
    const ratio = (Math.max(lum(fg), lum(bg)) + 0.05) / (Math.min(lum(fg), lum(bg)) + 0.05);
    const size = parseFloat(cs.fontSize), large = size >= 24 || (size >= 18.66 && +cs.fontWeight >= 700);
    if (ratio < (large ? 3 : 4.5)) out.push({ ratio: +ratio.toFixed(2), text: text.slice(0, 30), cls: (el.className?.toString() || el.tagName).slice(0, 40), color: cs.color });
  }
  return { app: !!document.querySelector(".nav"), rows: document.querySelectorAll("table.grid tbody tr, .panel").length, out };
});

let failures = 0;
for (const theme of ["dark", "light"]) {
  const page = await ctx.newPage();
  await page.addInitScript(([t, e]) => localStorage.setItem("motionproof.ui", JSON.stringify({
    projectId: "PRJ_001", modelId: "MDL_001", experimentId: "EXP_001", theme: t, user: e })), [theme, process.env.MP_EMAIL]);
  const seen = new Map();
  let panels = 0;
  for (const key of SCREENS) {
    await page.goto(`${base}/#/${key}`);
    await page.waitForFunction(() => !document.body.innerText.includes("Loading"), null, { timeout: 60000 }).catch(() => undefined);
    await page.waitForTimeout(key === "workbench" ? 6000 : 2500);
    const r = await audit(page);
    if (!r.app) throw new Error(`the app did not render on ${key} (signed out?)`);
    panels += r.rows;
    for (const o of r.out) { const k = `${o.cls}|${o.color}`; seen.set(k, { ...o, n: (seen.get(k)?.n ?? 0) + 1, key }); }
  }
  const n = [...seen.values()].reduce((s, o) => s + o.n, 0);
  failures += n;
  console.log(`${theme}: ${SCREENS.length} screens, ${panels} panels and rows checked, ${n} low-contrast text nodes`);
  for (const o of [...seen.values()].sort((a, b) => b.n - a.n).slice(0, 12)) console.log(`  ${String(o.n).padStart(3)}x ${o.ratio}  ${o.cls}  ${o.color}  "${o.text}"  (${o.key})`);
  await page.close();
}
await browser.close();
process.exit(failures ? 1 : 0);
