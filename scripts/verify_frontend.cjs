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
  assert.equal(account.synthetic_owner, true, "Use only a fresh synthetic owner");
  fs.mkdirSync(output, { recursive: true });
  const checks = [];
  const errors = [];
  const browser = await chromium.launch({
    headless: true,
    executablePath: process.env.DEERMATE_BROWSER_EXECUTABLE,
    args:
      process.env.DEERMATE_BROWSER_CONTAINER === "1" ? ["--no-sandbox"] : [],
  });
  try {
    const context = await browser.newContext({
      viewport: { width: 1440, height: 1080 },
      locale: "zh-CN",
    });
    let submissions=0;
    await context.route("**/api/**",route=>{const r=route.request();if(r.method()==="POST"&&/\/runs(?:\/|$)|\/router\/messages$/.test(new URL(r.url()).pathname)){submissions++;return route.abort();}return route.continue();});
    await context.addCookies([{ name: "locale", value: "zh-CN", url: base }]);
    const page = await context.newPage();
    page.on("pageerror", (error) => errors.push(error.message.slice(0, 300)));
    await page.goto(`${base}/login`);
    await page.locator("#email").waitFor();
    assert.equal(
      await page.getByRole("heading", { level: 1 }).evaluate((el) => {
        const font = getComputedStyle(el).fontFamily.toLowerCase();
        return font.includes("sans-serif") && !font.includes("georgia");
      }),
      true,
    );
    checks.push("design_login_heading_uses_shared_sans_font");
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
    await page.locator("[data-testid~=desk]").waitFor();
    assert.equal(
      (await page.request.get(`${base}/api/v1/auth/me`)).status(),
      200,
    );
    checks.push("real_owner_login");
    const surface = page.locator("[data-testid~=desk]");
    async function expectSurface() {
      const colors = await surface.evaluate((el) => {
        const probe = document.createElement("div");
        probe.style.background = "var(--ds-colors-canvas-soft)";
        el.append(probe);
        const result = [
          getComputedStyle(el).backgroundColor,
          getComputedStyle(probe).backgroundColor,
        ];
        probe.remove();
        return result;
      });
      assert.equal(colors[0], colors[1]);
    }
    await expectSurface();
    assert.equal(
      await page
        .getByRole("heading", { level: 1 })
        .evaluate((el) => getComputedStyle(el).fontFamily.includes("Georgia")),
      false,
    );
    checks.push("design_neutral_theme_and_shared_sans_typography");
    assert.equal(
      new URL((await page.request.get(base + "/")).url()).pathname,
      "/workspace",
    );
    assert.equal(
      (await page.request.get(base + "/api/mcp/config")).status(),
      200,
    );
    checks.push("private_default_entry_and_managed_mcp_configuration");
    await page.screenshot({
      path: path.join(output, "workspace.png"),
      fullPage: true,
    });
    await page.goto(base + "/workspace/work");
    const taskRows = page.getByTestId("work-record-row");
    await taskRows.first().waitFor();
    const rows = await taskRows.count();
    assert(rows > 0);
    const opener = taskRows
      .first()
      .getByRole("button", { name: "查看详情", exact: true });
    await opener.click();
    await page.getByTestId("task-detail").waitFor();
    await page.screenshot({
      path: path.join(output, "evidence.png"),
      fullPage: true,
    });
    await page.keyboard.press("Escape");
    await page.getByTestId("task-detail").waitFor({ state: "hidden" });
    assert(await opener.evaluate((el) => el === document.activeElement));
    checks.push("real_task_evidence_escape_and_focus_restore");
    const active = page.getByRole("tab", { name: /处理中/ });
    await active.click();
    await active.press("ArrowRight");
    await page.waitForFunction(()=>[...document.querySelectorAll('[role="tab"]')].some(e=>e.textContent.includes("已结束")&&e.getAttribute("aria-selected")==="true"));
    assert.equal(
      await page
        .getByRole("tab", { name: /已结束/ })
        .getAttribute("aria-selected"),
      "true",
    );
    checks.push("status_filter_keyboard_navigation");
    await page.goto(base + "/workspace");
    const text = "前端草稿验收：只准备目标，不启动模型执行。";
    await page.getByTestId("message-input").fill(text);
    assert.equal(new URL(page.url()).search, "");
    await page.goto(base + "/workspace/chats/new");
    const chatDraft = page.locator("textarea[name=message]");
    await chatDraft.fill(text);
    assert.equal(await chatDraft.inputValue(), text);
    assert.equal(new URL(page.url()).search, "");
    checks.push(
      "home_and_chat_drafts_keep_prompt_out_of_url_without_submission",
    );
    await page.goto(base + "/workspace");
    await page.getByTestId("message-input").waitFor();
    await page.emulateMedia({ colorScheme: "dark" });
    await page.waitForFunction(() =>
      document.documentElement.classList.contains("dark"),
    );
    await expectSurface();
    await page.screenshot({
      path: path.join(output, "dark.png"),
      fullPage: true,
    });
    checks.push("dark_surface_matches_semantic_palette");
    await page.emulateMedia({ colorScheme: "light", reducedMotion: "reduce" });
    await page.reload();
    assert.equal(
      await page
        .getByRole("button", { name: "临时对话", exact: true })
        .evaluate((el) => getComputedStyle(el).transitionDuration),
      "0s",
    );
    checks.push("reduced_motion_removes_control_transitions");
    await page.setViewportSize({ width: 390, height: 844 });
    await page.getByTestId("message-input").waitFor();
    assert(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    );
    const trigger = page
      .getByTestId("topbar")
      .locator("[data-sidebar=trigger]");
    await trigger.click();
    await page.getByRole("dialog").waitFor();
    await page.keyboard.press("Escape");
    await page.getByRole("dialog").waitFor({ state: "hidden" });
    assert(await trigger.evaluate((el) => el === document.activeElement));
    assert(
      await page
        .getByTestId("message-input")
        .evaluate((el) => parseFloat(getComputedStyle(el).fontSize) >= 16),
    );
    assert(
      await page
        .getByRole("button", { name: "发送", exact: true })
        .evaluate((el) => el.getBoundingClientRect().height >= 44),
    );
    await page.screenshot({
      path: path.join(output, "mobile.png"),
      fullPage: true,
    });
    checks.push("mobile_navigation_focus_readable_input_and_touch_targets");
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
    await faultPage.goto(`${base}/workspace/work`);
    await faultPage
      .getByRole("alert")
      .filter({ hasText: /有些记录暂时没读到|Some records/ })
      .waitFor({ timeout: 20000 });
    assert(await faultPage.getByTestId("work-search").isEnabled());
    checks.push("fault_injection_preserves_unknown_and_partial_states");
    await faultContext.close();
    assert.equal(
      (await page.request.get(`${base}/api/v1/auth/me`)).headers()[
        "x-deermate-backend"
      ],
      "go",
    );
    checks.push("go_owns_browser_authentication");
    await page.setViewportSize({ width: 1440, height: 1080 });
    await page.goto(`${base}/admin`);
    await page.getByRole("heading", { name: "管理工作台" }).waitFor();
    assert.equal(
      await page
        .locator("body")
        .evaluate((el) => getComputedStyle(el).backgroundColor),
      "rgb(250, 250, 250)",
    );
    const email = `browser-${require("node:crypto").randomBytes(6).toString("hex")}@example.com`;
    await page.getByLabel("邮箱", { exact: true }).fill(email);
    await page
      .getByLabel("初始密码")
      .fill(require("node:crypto").randomBytes(24).toString("hex"));
    const creation = page.waitForResponse(
      (r) =>
        r.url().endsWith("/api/v1/admin/users") &&
        r.request().method() === "POST",
    );
    await page.getByRole("button", { name: "创建账号", exact: true }).click();
    const created = await creation;
    assert.equal(created.status(), 201);
    const member = await created.json();
    try {
      const row = page.locator("#users tr").filter({ hasText: email });
      await row.getByRole("button", { name: "重置密码", exact: true }).click();
      await page.locator("#password-reset").waitFor();
      assert.equal(
        await page.locator("#reset-password").getAttribute("type"),
        "password",
      );
      await page.keyboard.press("Escape");
      await page.locator("#password-reset").waitFor({ state: "hidden" });
      await page.waitForFunction(
        () => document.activeElement?.textContent === "重置密码",
      );
      checks.push("design_admin_password_dialog_escape_and_focus_return");
      await row.getByRole("button", { name: "重置密码", exact: true }).click();
      await page
        .locator("#reset-password")
        .fill(require("node:crypto").randomBytes(24).toString("hex"));
      const resetResponse = page.waitForResponse(
        (r) =>
          r.url().endsWith(`/api/v1/admin/users/${member.id}/password`) &&
          r.request().method() === "POST",
      );
      await page.getByRole("button", { name: "保存密码", exact: true }).click();
      assert.equal((await resetResponse).status(), 200);
      await page.locator("#password-reset").waitFor({ state: "hidden" });
      checks.push("design_admin_password_reset_submits_masked_form");
      await row.getByRole("button", { name: "停用", exact: true }).click();
      await row.getByText("已停用", { exact: true }).waitFor();
      checks.push("go_admin_console_creates_and_suspends_user");
      await page.screenshot({
        path: path.join(output, "admin.png"),
        fullPage: true,
      });
      await page.emulateMedia({ colorScheme: "dark" });
      await page.waitForFunction(() =>
        document.documentElement.classList.contains("dark"),
      );
      assert.equal(
        await page
          .locator("body")
          .evaluate((el) => getComputedStyle(el).backgroundColor),
        "rgb(17, 17, 17)",
      );
      await page.screenshot({
        path: path.join(output, "admin-dark.png"),
        fullPage: true,
      });
      checks.push("design_go_admin_uses_shared_light_dark_tokens");
    } finally {
      const csrf = (await context.cookies()).find(
        (c) => c.name === "csrf_token",
      ).value;
      const cleanup = await page.request.patch(
        `${base}/api/v1/admin/users/${member.id}`,
        {
          headers: { "X-CSRF-Token": csrf },
          data: { disabled: true },
        },
      );
      assert.equal(cleanup.status(), 200);
    }
    assert.equal(submissions,0);
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
  console.error(error.stack ?? error.message);
  process.exitCode = 1;
});
