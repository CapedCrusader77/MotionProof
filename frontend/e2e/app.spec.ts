import { expect, test, type Page } from "@playwright/test";

// End-to-end tests against the real backend and a fresh workspace (see playwright.config.ts).
// They drive the UI the way an engineer would and fail on any uncaught page error or a screen
// that falls into its error boundary.

const ROUTES = ["projects", "import", "workbench", "features", "tolerances", "process", "virtual",
  "mechanics", "asbuilt", "hardware", "calibration", "builder", "monitor", "adaptive", "robustness",
  "sensitivity", "investigate", "worstcase", "workspace", "degradation", "fidelity", "challenge",
  "optimisation", "comparison", "trust", "reports", "benchmarks", "external", "settings"];

function watchErrors(page: Page): string[] {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(`pageerror: ${e.message}`));
  return errors;
}

test.describe.configure({ mode: "serial" });

// The app shows the public homepage until someone signs in. Sign-in is a local session, so the
// tests start signed in and keep whatever other UI state a test sets.
test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => {
    try {
      const key = "motionproof.ui";
      const state = JSON.parse(localStorage.getItem(key) ?? "{}");
      if (!state.user) { state.user = "e2e@lab.org"; localStorage.setItem(key, JSON.stringify(state)); }
    } catch { /* storage unavailable */ }
  });
});

test("shell loads and reports the backend healthy", async ({ page }) => {
  const errors = watchErrors(page);
  await page.goto("/");
  await expect(page.getByRole("navigation", { name: "Main navigation" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Projects", exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Benchmarks" })).toBeVisible();
  expect(errors).toEqual([]);
});

test("create a project and add the reference design through the UI", async ({ page }) => {
  const errors = watchErrors(page);
  await page.goto("/#/projects");
  await page.getByRole("button", { name: /New project|Create the first project/ }).first().click();
  await page.getByLabel("Name").fill("E2E project");
  await page.getByRole("button", { name: "Create", exact: true }).click();
  await expect(page.getByText("E2E project").first()).toBeVisible();
  await page.getByRole("button", { name: "Add reference design" }).click();
  // geometry generation with the CAD kernel can take a while
  await expect(page.getByText("synthetic").first()).toBeVisible({ timeout: 90_000 });
  expect(errors).toEqual([]);
});

test("every screen renders with a project and model selected", async ({ page, request }) => {
  const projects = await (await request.get("/api/v1/projects")).json();
  const project = projects.find((p: { name: string }) => p.name === "E2E project");
  expect(project, "project created by the previous test").toBeTruthy();
  const detail = await (await request.get(`/api/v1/projects/${project.id}`)).json();
  const modelId = detail.models[0].id;
  await page.addInitScript(([p, m]) => {
    localStorage.setItem("motionproof.ui", JSON.stringify({ projectId: p, modelId: m, theme: "light", user: "e2e@lab.org" }));
  }, [project.id, modelId]);
  const errors = watchErrors(page);
  for (const route of ROUTES) {
    await page.goto(`/#/${route}`);
    await page.waitForLoadState("networkidle");
    await expect(page.locator("main.main")).not.toBeEmpty();
    await expect(page.getByText("This screen failed to render"), `screen ${route}`).toHaveCount(0);
  }
  expect(errors).toEqual([]);
});

test("a screen that needs a model offers the workspace's models and opens on a pick", async ({ page }) => {
  const errors = watchErrors(page);
  await page.goto("/#/tolerances");
  await expect(page.getByText("Tolerances works on a model. Choose one to continue.")).toBeVisible();
  const pick = page.locator(".pick-list button").filter({ hasText: "synthetic reference" }).first();
  await expect(pick).toBeVisible();
  await pick.click();
  await expect(page.getByText("Choose one to continue.")).toHaveCount(0);
  await expect(page.getByRole("heading", { name: "Manufacturing tolerances" })).toBeVisible();
  // the selection persists
  await page.reload();
  await expect(page.getByRole("heading", { name: "Manufacturing tolerances" })).toBeVisible();
  expect(errors).toEqual([]);
});

test("command palette navigates", async ({ page }) => {
  await page.goto("/#/projects");
  await page.keyboard.press("Control+k");
  const box = page.getByRole("dialog").getByRole("textbox").first();
  await expect(box).toBeVisible();
  await box.fill("Benchmarks");
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(/#\/benchmarks/);
});

test("theme toggle switches and persists", async ({ page }) => {
  await page.goto("/#/projects");
  const before = await page.evaluate(() => document.documentElement.dataset.theme);
  await page.getByRole("button", { name: /Switch to (dark|light) theme/ }).click();
  const after = await page.evaluate(() => document.documentElement.dataset.theme);
  expect(after).not.toBe(before);
  await page.reload();
  expect(await page.evaluate(() => document.documentElement.dataset.theme)).toBe(after);
});

test("invalid tolerance input is reported, not accepted", async ({ request }) => {
  const r = await request.post("/api/v1/tolerances", { data: { not_a_field: 1 } });
  expect(r.status()).toBeGreaterThanOrEqual(400);
  expect(r.status()).toBeLessThan(500);
});

test("layout has no horizontal overflow at phone width", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/#/projects");
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  expect(overflow).toBeLessThanOrEqual(1);
});
