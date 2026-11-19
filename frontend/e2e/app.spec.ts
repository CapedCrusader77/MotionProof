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

// The app shows the public homepage until someone signs in. Each test opens a real server
// session for the test account (registered once) and marks the browser as signed in.
const ACCOUNT = { email: "e2e@lab.org", password: "e2e-password-1" };
test.beforeEach(async ({ page }) => {
  const r = await page.request.post("/api/v1/auth/register", { data: ACCOUNT });
  if (r.status() === 409) expect((await page.request.post("/api/v1/auth/login", { data: ACCOUNT })).ok()).toBe(true);
  else expect(r.status()).toBe(201);
  await page.addInitScript((email) => {
    try {
      const key = "motionproof.ui";
      const state = JSON.parse(localStorage.getItem(key) ?? "{}");
      if (!state.user) { state.user = email; localStorage.setItem(key, JSON.stringify(state)); }
    } catch { /* storage unavailable */ }
  }, ACCOUNT.email);
});

test("sign-in checks the password against the server", async ({ browser }) => {
  const context = await browser.newContext();
  const page = await context.newPage();
  await page.goto("/#/signin");
  await page.getByLabel("Email").fill(ACCOUNT.email);
  await page.getByLabel("Password", { exact: true }).fill("not-the-password");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("not correct");
  await page.getByLabel("Password", { exact: true }).fill(ACCOUNT.password);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(page.getByRole("navigation", { name: "Main navigation" })).toBeVisible();
  await context.close();
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

test("every screen renders with a project and model selected", async ({ page }) => {
  const request = page.request;
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

async function selectReferenceModel(page: Page) {
  const projects = await (await page.request.get("/api/v1/projects")).json();
  const project = projects.find((p: { name: string }) => p.name === "E2E project");
  const detail = await (await page.request.get(`/api/v1/projects/${project.id}`)).json();
  await page.addInitScript(([p, m]) => {
    localStorage.setItem("motionproof.ui", JSON.stringify({ projectId: p, modelId: m, theme: "dark", user: "e2e@lab.org" }));
  }, [project.id, detail.models[0].id]);
}

// Launch real runs from the screens and wait for their results (small budgets keep them short).
test("process batch runs from the UI", async ({ page }) => {
  const errors = watchErrors(page);
  await selectReferenceModel(page);
  await page.goto("/#/process");
  const add = page.getByLabel("Add feature");
  await add.selectOption({ index: 1 });
  await page.getByPlaceholder("e.g. CNC turning").fill("CNC turning");
  await page.getByLabel("Standard deviation").fill("0.003");
  await page.getByRole("button", { name: "Generate" }).click();
  await expect(page.getByText(/variance|Cpk|batch/i).last()).toBeVisible({ timeout: 120_000 });
  await expect(page.locator(".toast.error, .toasts .error")).toHaveCount(0);
  expect(errors).toEqual([]);
});

test("adaptive experiment runs from the UI", async ({ page }) => {
  test.setTimeout(300_000);
  const errors = watchErrors(page);
  await selectReferenceModel(page);
  await page.goto("/#/adaptive");
  await page.getByLabel("Limit (SI)").fill("0.005");
  await page.getByLabel("Initial simulations").fill("6");
  await page.getByLabel("Simulation budget").fill("8");
  await page.getByLabel("Population").fill("200");
  await page.getByRole("button", { name: "Run", exact: true }).click();
  await expect(page.getByText(/^Result /)).toBeVisible({ timeout: 280_000 });
  await expect(page.getByText("Surrogate PREDICTION").first()).toBeVisible();
  expect(errors).toEqual([]);
});

test("degradation projection runs from the UI", async ({ page }) => {
  test.setTimeout(300_000);
  const errors = watchErrors(page);
  await selectReferenceModel(page);
  await page.goto("/#/degradation");
  await page.getByLabel("Add mechanism").selectOption("backlash");
  await page.getByLabel("Rate per cycle").fill("0.000000001");
  await page.getByLabel("≤ limit (SI)").fill("0.01");
  await page.getByLabel("Cycles", { exact: true }).fill("0, 500000, 1000000");
  await page.getByRole("button", { name: "Project", exact: true }).click();
  await expect(page.getByText(/MODEL-BASED PROJECTION/).first()).toBeVisible({ timeout: 280_000 });
  expect(errors).toEqual([]);
});

test("account panel changes the password", async ({ page }) => {
  await page.goto("/#/settings");
  await expect(page.getByText("Administrator").first()).toBeVisible();
  await page.getByLabel("Current password").fill(ACCOUNT.password);
  await page.getByLabel("New password", { exact: true }).fill("e2e-password-2");
  await page.getByLabel("New password again").fill("e2e-password-2");
  await page.getByRole("button", { name: "Change password" }).click();
  await expect(page.getByText(/Password changed/)).toBeVisible();
  // put it back so later tests can sign in
  await page.getByLabel("Current password").fill("e2e-password-2");
  await page.getByLabel("New password", { exact: true }).fill(ACCOUNT.password);
  await page.getByLabel("New password again").fill(ACCOUNT.password);
  await page.getByRole("button", { name: "Change password" }).click();
  await expect(page.getByText(/Password changed/).first()).toBeVisible();
});

test("a screen whose file vanished after a rebuild reloads and opens", async ({ page }) => {
  await selectReferenceModel(page);
  let blocked = 0;
  await page.route(/manufacturing-[^/]*\.js$/, (route) => (blocked++ === 0 ? route.fulfill({ status: 404, body: "" }) : route.continue()));
  await page.goto("/#/tolerances");
  await expect(page.getByRole("heading", { name: "Manufacturing tolerances" })).toBeVisible({ timeout: 30_000 });
  expect(blocked).toBeGreaterThanOrEqual(2);
});

test("command palette navigates", async ({ page }) => {
  await page.goto("/#/projects");
  // the shell (and its shortcut) mounts once the server has confirmed the session
  await expect(page.getByRole("navigation", { name: "Main navigation" })).toBeVisible();
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

test("invalid tolerance input is reported, not accepted", async ({ page }) => {
  const r = await page.request.post("/api/v1/tolerances", { data: { not_a_field: 1 } });
  expect(r.status()).toBeGreaterThanOrEqual(400);
  expect(r.status()).toBeLessThan(500);
});

test("layout has no horizontal overflow at phone width", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/#/projects");
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  expect(overflow).toBeLessThanOrEqual(1);
});
