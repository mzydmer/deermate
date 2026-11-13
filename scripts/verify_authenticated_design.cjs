const { inspector } = require("./frontend_test_helpers.cjs");
const fs = require("fs");
const assert = require("assert/strict");
const { chromium } = require(
  process.env.DEERMATE_PLAYWRIGHT_MODULE || "playwright",
);
const output = process.env.DEERMATE_OUTPUT || ".deermate/design-auth-20261106";
const base = process.env.DEERMATE_URL || "http://127.0.0.1:3300";
assert(["127.0.0.1", "localhost"].includes(new URL(base).hostname));
(async () => {
  const browser = await chromium.launch({
    headless: true,
    ...(process.env.DEERMATE_BROWSER_EXECUTABLE
      ? { executablePath: process.env.DEERMATE_BROWSER_EXECUTABLE }
      : {}),
  });
  const checks = [],
    failures = [],
    errors = [];
  let runAttempts = 0;
  try {
    const auth = await browser.newContext({ locale: "zh-CN" });
    assert.equal(
      (await (await auth.request.get(base + "/__visual-fixture")).json())
        .fixture,
      "design-auth-v1",
    );
    await auth.addCookies([{ name: "locale", value: "zh-CN", url: base }]);
    const p = await auth.newPage();
    const account = JSON.parse(fs.readFileSync(output + "/owner.json"));
    const setup = await p.request.get(base + "/api/v1/auth/setup-status");
    if ((await setup.json()).needs_setup)
      assert.equal(
        (
          await p.request.post(base + "/api/v1/auth/initialize", {
            data: { email: account.email, password: account.password },
          })
        ).status(),
        201,
      );
    await auth.clearCookies();
    await auth.addCookies([{ name: "locale", value: "zh-CN", url: base }]);
    await p.goto(base + "/login");
    await p.locator("#email").fill(account.email);
    await p.locator("#password").fill(account.password);
    await p.locator("button[type=submit]").click();
    await p.waitForURL((u) => u.pathname === "/workspace");
    assert.equal((await p.request.get(base + "/api/v1/auth/me")).status(), 200);
    checks.push("real_go_owner_login");
    const state = await auth.storageState();
    await auth.close();
    for (const width of [390, 768, 1024, 1280, 1440])
      for (const dark of [false, true]) {
        const context = await browser.newContext({
          viewport: { width, height: 1000 },
          locale: "zh-CN",
          colorScheme: dark ? "dark" : "light",
          reducedMotion: "reduce",
          storageState: state,
        });
        await context.addInitScript(
          (t) => localStorage.setItem("theme", t),
          dark ? "dark" : "light",
        );
        const page = await context.newPage();
        page.on("pageerror", (e) =>
          errors.push({ width, dark, message: e.message }),
        );
        await page.route("**/api/**", async (route) => {
          const r = route.request();
          if (
            r.method() === "POST" &&
            /\/runs(?:\/|$)/.test(new URL(r.url()).pathname)
          ) {
            runAttempts++;
            await route.abort();
          } else await route.continue();
        });
        async function check(name, fn) {
          try {
            await fn();
            checks.push({ name, width, dark });
          } catch (e) {
            failures.push({
              name,
              width,
              dark,
              error: e.message.slice(0, 500),
            });
            console.log("FAIL", name, width, dark, e.message.slice(0, 250));
            await page
              .screenshot({
                path: `${output}/FAIL-${name}-${width}-${dark}.png`,
                fullPage: true,
              })
              .catch(() => {});
          }
        }
        await check("workspace", async () => {
          await page.goto(base + "/workspace");
          await page.getByTestId("message-input").waitFor();
          assert.equal(
            await page.evaluate(
              () => document.documentElement.scrollWidth <= innerWidth,
            ),
            true,
          );
          const surface = await page
            .locator("[data-testid~=desk]")
            .evaluate((e) =>
              (() => {
                const probe = document.createElement("div");
                probe.style.backgroundColor = "var(--ds-colors-canvas-soft)";
                e.append(probe);
                const result = {
                  actual: getComputedStyle(e).backgroundColor,
                  expected: getComputedStyle(probe).backgroundColor,
                };
                probe.remove();
                return result;
              })(),
            );
          assert.equal(surface.actual, surface.expected);
          await page.screenshot({
            path: `${output}/workspace-${width}-${dark ? "dark" : "light"}.png`,
            fullPage: true,
          });
        });
        await check("task_filters_and_evidence", async () => {
          await page.goto(base + "/workspace/work");
          await page.getByTestId("work-record-row").first().waitFor();
          assert.equal(await page.getByTestId("work-record-row").count(), 6);
          await page.getByRole("tab", { name: /待回应/ }).click();
          assert.equal(await page.getByTestId("work-record-row").count(), 2);
          await page.getByRole("tab", { name: /已结束/ }).click();
          const opener = page
            .getByTestId("work-record-row")
            .first()
            .getByRole("button", { name: "查看详情" });
          await opener.click();
          const sheet = inspector(page);
          await sheet.waitFor();
          await page.getByTestId("task-detail").waitFor();
          if (width < 600) {
            const close = await page
              .getByRole("dialog")
              .getByRole("button", { name: "关闭", exact: true })
              .boundingBox();
            assert(close.width >= 44 && close.height >= 44);
          }
          await page.screenshot({
            path: `${output}/detail-${width}-${dark ? "dark" : "light"}.png`,
            fullPage: true,
          });
          await page.keyboard.press("Escape");
          await sheet.waitFor({ state: "hidden" });
          assert(await opener.evaluate((e) => e === document.activeElement));
        });
        await check("memory_settings_layout", async () => {
          await page.goto(base + "/workspace?settings=memory");
          const dialog = page.locator("[role=dialog]");
          await dialog.waitFor();
          await page.locator("[data-testid=settings-memory-page]").waitFor();
          await page.waitForTimeout(100);
          const selected = dialog.locator("nav [aria-current=page]");
          await selected.waitFor();
          const visible = await selected.evaluate((e) => {
            const a = e.getBoundingClientRect(),
              b = e.closest("nav").getBoundingClientRect();
            return a.left >= b.left - 1 && a.right <= b.right + 1;
          });
          assert(visible, "Selected navigation item must be visible");
          const v = await dialog.evaluate((e) => {
            const panel = e.querySelector('[data-testid="settings-content"]'),
              nav = e.querySelector("nav");
            return {
              w: e.getBoundingClientRect().width,
              scroll: e.scrollWidth,
              client: e.clientWidth,
              panel: panel?.getBoundingClientRect().toJSON(),
              nav: nav?.getBoundingClientRect().toJSON(),
            };
          });
          assert(v.scroll <= v.client + 1, JSON.stringify(v));
          assert(v.panel.height > 180, JSON.stringify(v));
          if (width < 960)
            assert(v.panel.width > v.client * 0.75, JSON.stringify(v));
          await page.screenshot({
            path: `${output}/memory-${width}-${dark ? "dark" : "light"}.png`,
            fullPage: true,
          });
          await page.keyboard.press("Escape");
          await dialog.waitFor({ state: "hidden" });
        });
        for (const section of [
          "account",
          "appearance",
          "models",
          "users",
          "notification",
          "channels",
          "subagents",
          "about",
        ])
          await check("settings_" + section, async () => {
            await page.goto(base + "/workspace?settings=" + section);
            const d = page.locator("[role=dialog]");
            await d.waitFor();
            await page.waitForTimeout(200);
            assert.equal(
              await d.evaluate((e) => e.scrollWidth <= e.clientWidth + 1),
              true,
            );
            if (width === 390 || width === 1440)
              await page.screenshot({
                path: `${output}/settings-${section}-${width}-${dark ? "dark" : "light"}.png`,
                fullPage: true,
              });
            await page.keyboard.press("Escape");
          });
        await check("chat_draft_only", async () => {
          await page.goto(base + "/workspace/chats/new");
          await page.locator("textarea,[role=textbox]").first().waitFor();
          await page
            .locator("textarea,[role=textbox]")
            .first()
            .fill("合成验收草稿，不发送。");
          assert.equal(
            await page.evaluate(
              () => document.documentElement.scrollWidth <= innerWidth,
            ),
            true,
          );
          await page.screenshot({
            path: `${output}/chat-${width}-${dark ? "dark" : "light"}.png`,
            fullPage: true,
          });
        });
        for (const route of ["/admin", "/admin/agents"])
          await check(
            route === "/admin" ? "admin" : "authorizations",
            async () => {
              await page.goto(base + route);
              await page.getByRole("heading", { level: 1 }).waitFor();
              await page.waitForTimeout(150);
              assert.equal(
                await page.evaluate(
                  () => document.documentElement.scrollWidth <= innerWidth,
                ),
                true,
              );
              await page.screenshot({
                path: `${output}/${route === "/admin" ? "admin" : "authorizations"}-${width}-${dark ? "dark" : "light"}.png`,
                fullPage: true,
              });
            },
          );
        await context.close();
      }
    fs.writeFileSync(
      output + "/authenticated.json",
      JSON.stringify(
        {
          checks,
          failures,
          errors,
          runAttempts,
          scope:
            "Actual Go login/production React/Go pages; synthetic loopback runtime for visual states. No real model/native execution.",
        },
        null,
        2,
      ),
    );
    console.log(
      JSON.stringify(
        {
          passed: checks.length,
          failed: failures.length,
          pageErrors: errors.length,
          runAttempts,
          failures: failures.slice(0, 8),
          errors: errors.slice(0, 6),
        },
        null,
        2,
      ),
    );
    if (failures.length || errors.length || runAttempts) process.exitCode = 1;
  } finally {
    await browser.close();
  }
})().catch((e) => {
  console.error(e);
  process.exit(1);
});
