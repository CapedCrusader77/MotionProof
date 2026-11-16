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
    localStorage.setItem("motionproof.ui", JSON.stringify({ projectId: p, modelId: m, theme: "light" }));
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

test("phone width: navigation is a drawer behind the menu button", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/#/projects");
  const nav = page.getByRole("navigation", { name: "Main navigation" });
  const menu = page.getByRole("button", { name: "Open navigation" });
  await expect(menu).toBeVisible();
  await expect(nav).not.toBeInViewport();
  await menu.click();
  await expect(nav).toBeInViewport();
  await nav.getByRole("button", { name: "Benchmarks" }).click();
  await expect(page).toHaveURL(/#\/benchmarks/);
  await expect(nav).not.toBeInViewport();
});

test("skip link is the first tab stop and backend status is shown", async ({ page }) => {
  await page.goto("/#/projects");
  await page.keyboard.press("Tab");
  await expect(page.getByRole("link", { name: "Skip to content" })).toBeFocused();
  await expect(page.getByRole("status").filter({ hasText: /backend ready|job running/ }).first()).toBeVisible();
});

test("external validation lists the four datasets with citations", async ({ page }) => {
  await page.goto("/#/external");
  for (const key of ["anchor-lab", "stuttgart-te", "nist-ur5", "kuka-kr300"]) {
    await expect(page.getByText(key, { exact: true })).toBeVisible();
  }
  await page.getByText("stuttgart-te", { exact: true }).click();
  await expect(page.getByText(/doi:10\.18419\/DARUS-5760/).first()).toBeVisible();
});

async function selectReferenceModel(page: Page, request: import("@playwright/test").APIRequestContext) {
  const projects = await (await request.get("/api/v1/projects")).json();
  const project = projects.find((p: { name: string }) => p.name === "E2E project");
  const detail = await (await request.get(`/api/v1/projects/${project.id}`)).json();
  await page.addInitScript(([p, m]) => {
    localStorage.setItem("motionproof.ui", JSON.stringify({ projectId: p, modelId: m, theme: "light" }));
  }, [project.id, detail.models[0].id]);
}

test("workbench: select, isolate, keyboard shading and readiness", async ({ page, request }) => {
  await selectReferenceModel(page, request);
  await page.goto("/#/workbench");
  await page.getByRole("treeitem", { name: /stage2_ring/ }).click();
  await expect(page.getByRole("complementary", { name: "Inspector" }).getByText("stage2_ring").first()).toBeVisible();
  await page.getByRole("button", { name: "Isolate stage2_ring" }).click();
  await expect(page.locator(".statusbar")).toContainText("Visible 1/20");
  const viewport = page.getByLabel(/3D viewport/);
  await viewport.focus();
  await page.keyboard.press("3");
  await expect(page.getByRole("button", { name: "Wire", exact: true })).toHaveAttribute("aria-pressed", "true");
  await page.getByRole("tab", { name: /Readiness/ }).click();
  await expect(page.locator(".check-row").first()).toBeVisible();
});

test("tolerances: row opens the real distribution against its limits", async ({ page, request }) => {
  await selectReferenceModel(page, request);
  await page.goto("/#/tolerances");
  await expect(page.locator("svg.spark").first()).toBeVisible();
  await page.getByRole("row", { name: /^s2_backlash_sp/ }).click();
  const insp = page.getByRole("complementary", { name: "Tolerance inspector" });
  await expect(insp.getByText("Distribution against limits")).toBeVisible();
  await expect(insp.getByText("0.025 … 0.055 mm", { exact: true })).toBeVisible();
  await page.getByRole("tab", { name: /Fits/ }).click();
  await expect(page.getByText("shaft_in_bearing")).toBeVisible();
});

test("virtual assemblies: generate, compare and inspect deviations", async ({ page, request }) => {
  await selectReferenceModel(page, request);
  await page.goto("/#/virtual");
  await page.getByRole("button", { name: "Generate" }).click();
  const first = page.locator(".va-body table.grid tbody tr").first();
  await expect(first).toBeVisible({ timeout: 90_000 });
  await first.click();
  await expect(page.getByRole("radio", { name: "Overlay" })).toBeEnabled();
  await page.getByRole("radio", { name: "Overlay" }).click();
  await page.getByRole("tab", { name: "Deviations" }).click();
  await expect(page.locator(".zone").first()).toBeVisible({ timeout: 60_000 });
});
