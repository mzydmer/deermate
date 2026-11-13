const { memoryAction, seedMemory } = require("./frontend_test_helpers.cjs");
/* Real Go/React workspace acceptance. Read-only matrix blocks model submissions.
   Functional checks only use an isolated synthetic owner's memory and empty chats. */
const fs = require("fs");
const assert = require("assert/strict");
const { chromium } = require(
  process.env.DEERMATE_PLAYWRIGHT_MODULE || "playwright",
);
const base = process.env.DEERMATE_URL;
const output = process.env.DEERMATE_OUTPUT;
assert(
  base && output && ["localhost", "127.0.0.1"].includes(new URL(base).hostname),
);
const owner = JSON.parse(fs.readFileSync(output + "/owner.json"));
assert(owner.synthetic_owner === true && owner.origin === base);
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
  let modelSubmissions = 0;
  try {
    const auth = await browser.newContext({ locale: "zh-CN" });
    await auth.addCookies([{ name: "locale", value: "zh-CN", url: base }]);
    const page = await auth.newPage();
    await page.goto(base + "/login");
    await page.locator("#email").fill(owner.email);
    await page.locator("#password").fill(owner.password);
    await page.locator("button[type=submit]").click();
    await page.waitForURL((u) => u.pathname === "/workspace");
    await page.locator("[data-testid=message-input]").waitFor();
    checks.push({ name: "real_go_dom_login" });
    await seedMemory(page, auth, base, "Synthetic source and keyboard check");
    const state = await auth.storageState();
    await auth.close();
    async function runCheck(name, p, fn, meta = {}) {
      try {
        await fn();
        checks.push({ name, ...meta });
      } catch (e) {
        failures.push({ name, ...meta, error: e.message.slice(0, 500) });
        console.log("FAIL", name, meta.width ?? "", e.message.slice(0, 160));
        await p
          .screenshot({
            path: `${output}/FAIL-${name}-${meta.width ?? "functional"}-${meta.dark ?? "light"}.png`,
            fullPage: true,
          })
          .catch(() => {});
      }
    }
    for (const width of [390, 768, 1024, 1280, 1440])
      for (const dark of [false, true]) {
        const context = await browser.newContext({
          storageState: state,
          viewport: { width, height: 1000 },
          locale: "zh-CN",
          colorScheme: dark ? "dark" : "light",
          reducedMotion: "reduce",
        });
        await context.addInitScript(
          (theme) => localStorage.setItem("theme", theme),
          dark ? "dark" : "light",
        );
        const p = await context.newPage();
        p.on("pageerror", (e) =>
          errors.push({ width, dark, message: e.message }),
        );
        await p.route("**/api/**", async (route) => {
          const request = route.request();
          if (
            request.method() === "POST" &&
            (/\/runs(?:\/|$)/.test(new URL(request.url()).pathname) ||
              new URL(request.url()).pathname === "/api/me/router/messages")
          ) {
            modelSubmissions++;
            await route.abort();
          } else await route.continue();
        });
        for (const [route, title] of [
          ["/workspace", null],
          ["/workspace/work", "我的工作"],
          ["/workspace/memory", "关于你"],
        ])
          await runCheck(
            route.split("/").pop() || "home",
            p,
            async () => {
              await p.goto(base + route);
              await p.locator("[data-testid~=assistant]").waitFor();
              if (title)
                await p
                  .getByRole("heading", { name: title, exact: true })
                  .waitFor();
              else {
                await p.locator("[data-testid=message-input]").waitFor();
                await p
                  .getByText("在看最近的事…", { exact: true })
                  .waitFor({ state: "hidden" });
                await p
                  .getByText("正在读取记忆…", { exact: true })
                  .waitFor({ state: "hidden" });
              }
              assert(
                await p.evaluate(
                  () => document.documentElement.scrollWidth <= innerWidth,
                ),
                "page overflow",
              );
              assert.equal(
                await p
                  .locator("html")
                  .evaluate(
                    (el, d) => el.classList.contains("dark") === d,
                    dark,
                  ),
                true,
              );
              if (route === "/workspace") {
                assert.equal(
                  await p.locator("main textarea").count(),
                  1,
                  "one main composer",
                );
                assert(
                  (await p.locator("[data-testid~=focus-card]").count()) <= 3,
                );
                const area = await p
                  .locator("[data-testid=message-input]")
                  .boundingBox();
                assert(area.width > 200);
                if (width === 390) {
                  assert(
                    area.y + area.height < 1000,
                    "mobile composer stays in first viewport",
                  );
                  const toggle = p.getByRole("button", {
                    name: /先看看这几件事/,
                  });
                  if (await toggle.count())
                    assert.equal(
                      await toggle.getAttribute("aria-expanded"),
                      "false",
                    );
                }
                await p.screenshot({
                  path: `${output}/workspace-${width}-${dark ? "dark" : "light"}.png`,
                  fullPage: true,
                });
              }
            },
            { width, dark },
          );
        if (width === 390)
          await runCheck(
            "mobile_navigation_keyboard",
            p,
            async () => {
              await p.goto(base + "/workspace");
              const trigger = p.locator(
                "[data-testid~=topbar] [data-slot=sidebar-trigger]",
              );
              await trigger.focus();
              await p.keyboard.press("Enter");
              await p.getByRole("dialog").waitFor();
              await p.keyboard.press("Escape");
              await p.waitForFunction(
                () => !document.querySelector("[data-state=open][role=dialog]"),
              );
              await p.waitForTimeout(200);
              assert(
                await trigger.evaluate((el) => el === document.activeElement),
              );
              const hit = await trigger.boundingBox();
              assert(
                hit.width >= 44 && hit.height >= 44,
                "sidebar trigger hit area",
              );
            },
            { width, dark },
          );
        await context.close();
      }
    const c = await browser.newContext({
      storageState: state,
      viewport: { width: 1280, height: 1000 },
      locale: "zh-CN",
    });
    const p = await c.newPage();
    p.on("pageerror", (e) =>
      errors.push({ kind: "functional", message: e.message }),
    );
    await p.route("**/api/**", async (route) => {
      const r = route.request();
      if (
        r.method() === "POST" &&
        (/\/runs(?:\/|$)/.test(new URL(r.url()).pathname) ||
          new URL(r.url()).pathname === "/api/me/router/messages")
      ) {
        modelSubmissions++;
        await route.abort();
      } else await route.continue();
    });
    await runCheck("failed_refresh_keeps_composer", p, async () => {
      await p.route("**/api/me/workspace-snapshot", (route) =>
        route.fulfill({
          status: 503,
          contentType: "application/json",
          body: '{"detail":"synthetic read failure"}',
        }),
      );
      await p.goto(base + "/workspace");
      await p.getByText("最近的进展暂时没读到，仍然可以和我聊天。").waitFor();
      assert(await p.locator("[data-testid=message-input]").isEnabled());
      await p.unroute("**/api/me/workspace-snapshot");
      await p.getByRole("button", { name: "重试", exact: true }).click();
      await p
        .getByText("最近的进展暂时没读到，仍然可以和我聊天。")
        .waitFor({ state: "hidden" });
    });
    await runCheck("memory_source_keyboard_and_failure_mask", p, async () => {
      await p.goto(base + "/workspace/memory");
      const button = p
        .getByRole("button", { name: "查看来源与用途", exact: true })
        .first();
      await button.waitFor();
      await button.click();
      const dialog = p.getByRole("dialog");
      await dialog.waitFor();
      await dialog.getByText("最近用在哪些对话", { exact: true }).waitFor();
      await p.route("**/api/me/memories/*/source", (route) =>
        route.fulfill({
          status: 404,
          contentType: "application/json",
          body: '{"detail":"synthetic revoked source"}',
        }),
      );
      await dialog.getByText("暂时没读到来源。").waitFor({ timeout: 12000 });
      assert.equal(
        await dialog.locator("blockquote").count(),
        0,
        "failed source body masked",
      );
      await p.unroute("**/api/me/memories/*/source");
      await p.keyboard.press("Escape");
      await dialog.waitFor({ state: "hidden" });
      await p.waitForTimeout(200);
      assert(await button.evaluate((el) => el === document.activeElement));
    });
    await runCheck("memory_create_correct_forget", p, async () => {
      await p.goto(base + "/workspace/memory");
      await p
        .locator("[data-testid~=memory-content]")
        .fill("我习惯在周一整理笔记");
      await p.getByRole("button", { name: "保存记忆", exact: true }).click();
      const row = p
        .locator("[data-testid~=memory-list]>li")
        .filter({ hasText: "我习惯在周一整理笔记" });
      await row.waitFor();
      await memoryAction(p, row, "纠正");
      await p
        .locator("[data-testid~=memory-content]")
        .fill("我习惯在周五整理笔记");
      await p.getByRole("button", { name: "保存记忆", exact: true }).click();
      const corrected = p
        .locator("[data-testid~=memory-list]>li")
        .filter({ hasText: "我习惯在周五整理笔记" });
      await corrected.waitFor();
      await memoryAction(p, corrected, "忘记");
      await corrected.waitFor({ state: "hidden" });
    });
    await runCheck("temporary_creation_lost_ack_same_topic", p, async () => {
      await p.goto(base + "/workspace");
      const ids = [];
      let lost = false;
      await p.route("**/api/me/temporary-topics", async (route) => {
        ids.push(route.request().postDataJSON().operation_id);
        const response = await route.fetch();
        assert.equal(response.status(), 200);
        if (!lost) {
          lost = true;
          await route.fulfill({
            status: 502,
            contentType: "application/json",
            body: '{"detail":"synthetic lost acknowledgement"}',
          });
        } else await route.fulfill({ response });
      });
      await p.getByRole("button", { name: "临时对话", exact: true }).click();
      await p
        .getByText("临时对话还没创建成功。再点一次会核对同一个对话。")
        .waitFor();
      await p.reload();
      await p.locator("[data-testid=message-input]").waitFor();
      await p.getByRole("button", { name: "临时对话", exact: true }).click();
      await p.waitForURL((u) =>
        u.pathname.startsWith("/workspace/chats/temporary-"),
      );
      await p
        .getByText("临时对话 · 不读取或新增长期记忆，聊天记录仍会保存。")
        .waitFor();
      assert.equal(ids.length, 2);
      assert.equal(ids[0], ids[1]);
      await p.unroute("**/api/me/temporary-topics");
    });
    await runCheck("profile_name_timezone", p, async () => {
      const me = await (await p.request.get(base + "/api/v1/auth/me")).json();
      const profile = await (
        await p.request.get(base + "/api/me/personal-profile")
      ).json();
      const token = (await c.cookies()).find(
        (v) => v.name === "csrf_token",
      ).value;
      const result = await p.request.patch(base + "/api/me/personal-profile", {
        headers: { "X-CSRF-Token": token, "X-Expected-User-Id": me.id },
        data: {
          display_name: "验收同学",
          timezone: "Asia/Shanghai",
          expected_revision: profile.revision,
        },
      });
      assert.equal(result.status(), 200);
      await p.goto(base + "/workspace");
      await p.getByRole("heading", { name: /验收同学/ }).waitFor();
      const snapshot = await (
        await p.request.get(base + "/api/me/workspace-snapshot")
      ).json();
      if (snapshot.items.length) {
        const value = snapshot.items[0].evidence.occurred_at.replace(" ", "T");
        const normalized = /[zZ]$|[+-]\d\d:\d\d$/.test(value)
          ? value
          : value + "Z";
        const expected = new Intl.DateTimeFormat("zh-CN", {
          timeZone: "Asia/Shanghai",
          dateStyle: "medium",
          timeStyle: "short",
        }).format(new Date(normalized));
        const time = p.getByTestId("relative-time").first();
        await time.focus();
        await p
          .getByRole("tooltip")
          .getByText(expected, { exact: true })
          .waitFor();
      }
    });
    await c.close();
    const zoom = await browser.newContext({
      storageState: state,
      locale: "zh-CN",
      viewport: { width: 640, height: 500 },
      deviceScaleFactor: 2,
      reducedMotion: "reduce",
    });
    const zp = await zoom.newPage();
    await runCheck("200_percent_equivalent_reflow", zp, async () => {
      await zp.goto(base + "/workspace");
      await zp.locator("[data-testid=message-input]").waitFor();
      assert(
        await zp.evaluate(
          () => document.documentElement.scrollWidth <= innerWidth,
        ),
      );
      await zp.locator("[data-testid=message-input]").focus();
      assert(
        await zp
          .locator("[data-testid=message-input]")
          .evaluate((el) => el === document.activeElement),
      );
      await zp.screenshot({
        path: output + "/workspace-2x-reflow.png",
        fullPage: true,
      });
    });
    await zoom.close();
    assert.equal(
      modelSubmissions,
      0,
      "browser matrix must not submit provider/native work",
    );
  } finally {
    await browser.close();
  }
  const result = {
    passed: failures.length === 0 && errors.length === 0,
    checks,
    failures,
    page_errors: errors,
    model_submissions: modelSubmissions,
    scope:
      "Real Go login/storage and production React/Gateway; synthetic owner. Read matrix, memory writes and empty temporary topics; no provider/native submission.",
  };
  fs.writeFileSync(
    output + "/ui-receipt.json",
    JSON.stringify(result, null, 2) + "\n",
  );
  console.log(
    JSON.stringify({
      passed: result.passed,
      checks: checks.length,
      failures: failures.length,
      page_errors: errors.length,
    }),
  );
  assert(result.passed);
})().catch((e) => {
  console.error(e.message);
  process.exit(1);
});
