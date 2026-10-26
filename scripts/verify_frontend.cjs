/* Browser acceptance for the local profile. Uses generated owner credentials,
 * read-only task APIs and an isolated browser draft; never submits model work. */
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { chromium } = require(
  process.env.DEERMATE_PLAYWRIGHT_MODULE ?? "playwright-core",
);

async function main() {
  const base = process.env.DEERMATE_URL ?? "http://localhost:2026";
  const destination = new URL(base);
  if (
    !["localhost", "127.0.0.1", "nginx"].includes(destination.hostname) ||
    !["http:", "https:"].includes(destination.protocol) ||
    destination.username ||
    destination.password
  ) {
    throw new Error(
      "Frontend acceptance only sends owner credentials to the local profile",
    );
  }
  const output = process.env.DEERMATE_OUTPUT ?? "/tmp/deermate-ui";
  if (!process.env.DEERMATE_OWNER_FILE)
    throw new Error("Set DEERMATE_OWNER_FILE to the private local owner file");
  const account = JSON.parse(
    fs.readFileSync(process.env.DEERMATE_OWNER_FILE, "utf8"),
  );
  fs.mkdirSync(output, { recursive: true });
  const checks = [];
  const errors = [];
  const browser = await chromium.launch({
    headless: true,
    args:
      process.env.DEERMATE_BROWSER_CONTAINER === "1" ? ["--no-sandbox"] : [],
  });
  try {
    const context = await browser.newContext({
      viewport: { width: 1440, height: 1080 },
      locale: "zh-CN",
    });
    await context.addCookies([{ name: "locale", value: "zh-CN", url: base }]);
    const page = await context.newPage();
    page.on("pageerror", (error) => errors.push(error.message.slice(0, 300)));
    await page.goto(`${base}/login`);
    await page.locator("#email").waitFor();
    await page.screenshot({
      path: path.join(output, "login.png"),
      fullPage: true,
    });
    checks.push("deermate_login_rendered");
    await page.locator("#email").fill(account.email);
    await page.locator("#password").fill(account.password);
    await page.locator('button[type="submit"]').click();
    await page.waitForURL((url) => url.pathname === "/workspace", {
      timeout: 45000,
    });
    await page.locator(".dm-desk").waitFor();
    assert.equal(
      (await page.request.get(`${base}/api/v1/auth/me`)).status(),
      200,
    );
    checks.push("real_owner_login");
    assert.equal(
      new URL((await page.request.get(base + "/")).url()).pathname,
      "/workspace",
    );
    checks.push("default_entry_redirects_to_private_workspace");
    assert.equal(
      (await page.request.get(`${base}/api/mcp/config`)).status(),
      200,
    );
    checks.push("managed_mcp_configuration_readable");
    await page.waitForFunction(
      () =>
        document
          .querySelector('[role="tabpanel"]')
          ?.getAttribute("aria-busy") === "false",
    );
    await page.locator('.dm-hero [data-rendered="true"]').waitFor();
    await page.waitForTimeout(600);
    checks.push("self_hosted_lottie_rendered");
    await page.screenshot({
      path: path.join(output, "workspace.png"),
      fullPage: true,
    });
    assert.equal(await page.locator(".dm-fetch-error").count(), 0);
    checks.push("real_thread_task_queries_loaded");
    const rows = await page.locator(".dm-task-row").count();
    if (rows) {
      await page.locator(".dm-task-row").first().click();
      await page.locator(".dm-detail-body").waitFor();
      await page.waitForTimeout(500);
      await page.screenshot({
        path: path.join(output, "evidence.png"),
        fullPage: true,
      });
      checks.push("real_task_evidence_opened");
      await page.keyboard.press("Escape");
      await page.locator(".dm-details").waitFor({ state: "hidden" });
      checks.push("evidence_escape_dismissal");
      assert.equal(
        await page.evaluate(() =>
          document.activeElement?.classList.contains("dm-task-row"),
        ),
        true,
      );
      checks.push("evidence_dismissal_restores_keyboard_focus");
    }
    const active = page.getByRole("tab", { name: /^(进行中|Active)$/ });
    await active.click();
    assert.equal(await active.getAttribute("aria-selected"), "true");
    await active.press("ArrowRight");
    assert.equal(
      await page
        .getByRole("tab", { name: /^(已完成|Done)$/ })
        .getAttribute("aria-selected"),
      "true",
    );
    checks.push("status_filter_keyboard_navigation");
    await page.getByRole("tab", { name: /^(全部|All)$/ }).click();
    const text = "前端草稿验收：只准备目标，不启动模型执行。";
    await page.locator("#dm-goal").fill(text);
    await page
      .getByRole("button", { name: /^(准备对话|Prepare chat)$/ })
      .click();
    await page.waitForURL((url) => url.pathname === "/workspace/chats/new");
    await page.waitForFunction(
      (value) =>
        [...document.querySelectorAll('textarea,[role="textbox"]')].some(
          (element) => (element.value ?? element.textContent).includes(value),
        ),
      text,
    );
    assert.equal(new URL(page.url()).search, "");
    checks.push("account_scoped_draft_handoff_without_prompt_in_url");
    await page.goto(`${base}/workspace`);
    await page.locator(".dm-desk").waitFor();
    await page.emulateMedia({ colorScheme: "dark" });
    await page.waitForFunction(() =>
      document.documentElement.classList.contains("dark"),
    );
    await page.waitForTimeout(300);
    await page.screenshot({
      path: path.join(output, "dark.png"),
      fullPage: true,
    });
    checks.push("dark_theme_rendered");
    await page.emulateMedia({ colorScheme: "light", reducedMotion: "reduce" });
    await page.reload();
    await page.locator(".t-tabs-pill").waitFor();
    const reduced = await page
      .locator(".t-tabs-pill")
      .evaluate((element) => getComputedStyle(element).transitionDuration);
    assert.equal(reduced, "0s");
    assert.equal(
      await page
        .locator(".dm-hero .dm-brand-player")
        .evaluate((element) => getComputedStyle(element).display),
      "none",
    );
    checks.push("reduced_motion_static_brand_and_tabs");
    await page.setViewportSize({ width: 390, height: 844 });
    await page.waitForTimeout(300);
    assert.equal(
      await page
        .locator(".dm-desk")
        .evaluate((element) => element.scrollWidth <= element.clientWidth),
      true,
    );
    await page.screenshot({
      path: path.join(output, "mobile.png"),
      fullPage: true,
    });
    await page.locator('.dm-topbar [data-sidebar="trigger"]').click();
    await page.locator('[data-mobile="true"]').waitFor();
    await page.keyboard.press("Escape");
    checks.push("mobile_layout_and_navigation");
    const cookies = await context.cookies();
    const faultContext = await browser.newContext({
      viewport: { width: 1440, height: 1080 },
    });
    await faultContext.addCookies(cookies);
    await faultContext.route("**/api/models", (route) =>
      route.fulfill({
        status: 503,
        contentType: "application/json",
        body: '{"detail":"UI acceptance fault injection"}',
      }),
    );
    await faultContext.route("**/mcp-tasks?*", (route) =>
      route.fulfill({
        status: 503,
        contentType: "application/json",
        body: '{"detail":"UI acceptance fault injection"}',
      }),
    );
    const faultPage = await faultContext.newPage();
    faultPage.on("pageerror", (error) =>
      errors.push(error.message.slice(0, 300)),
    );
    await faultPage.goto(`${base}/workspace`);
    await faultPage
      .getByText(/暂时无法读取模型配置|Model configuration unavailable/)
      .waitFor({ timeout: 20000 });
    if (rows)
      await faultPage.locator(".dm-fetch-error").waitFor({ timeout: 20000 });
    checks.push("fault_injection_preserves_unknown_and_partial_states");
    await faultContext.close();
    assert.deepEqual(errors, []);
    checks.push("no_browser_page_errors");
    fs.writeFileSync(
      path.join(output, "receipt.json"),
      JSON.stringify(
        {
          passed: true,
          checks,
          existing_task_rows: rows,
          page_errors: errors,
          model_tasks_submitted: 0,
          limits: [
            "Local owner/login and read-only existing task evidence; no secretary model or cloud execution.",
            "Service errors are deliberate isolated browser route injections.",
          ],
        },
        null,
        2,
      ),
    );
    console.log(
      `PASS ${checks.length} frontend checks; ${rows} real task rows; no model task submitted.`,
    );
  } finally {
    await browser.close();
  }
}
main().catch((error) => {
  console.error(error.message);
  process.exitCode = 1;
});
