const { openProfile } = require("./frontend_test_helpers.cjs");
/* Visual state acceptance: refuses any origin without the isolated fixture marker. */
const { memoryAction, inspector } = require("./frontend_test_helpers.cjs");
const fs = require("node:fs");
const assert = require("node:assert/strict");
const { chromium } = require(
  process.env.DEERMATE_PLAYWRIGHT_MODULE || "playwright",
);
const base = process.env.DEERMATE_URL || "http://127.0.0.1:3300";
const output = process.env.DEERMATE_OUTPUT || ".deermate/design-auth-20261106";
assert(["127.0.0.1", "localhost"].includes(new URL(base).hostname));
(async () => {
  const browser = await chromium.launch({
    headless: true,
    ...(process.env.DEERMATE_BROWSER_EXECUTABLE
      ? { executablePath: process.env.DEERMATE_BROWSER_EXECUTABLE }
      : {}),
  });
  const checks = [];
  const errors = [];
  let runs = 0;
  try {
    const context = await browser.newContext({
      locale: "zh-CN",
      viewport: { width: 390, height: 844 },
      reducedMotion: "reduce",
    });
    const page = await context.newPage();
    page.on("pageerror", (e) => errors.push(e.message));
    await page.route("**/api/**", async (route) => {
      if (
        route.request().method() === "POST" &&
        /\/runs(?:\/|$)/.test(new URL(route.request().url()).pathname)
      ) {
        runs++;
        await route.abort();
      } else await route.continue();
    });
    assert.equal(
      (await (await page.request.get(base + "/__visual-fixture")).json())
        .fixture,
      "design-auth-v1",
    );
    const account = JSON.parse(fs.readFileSync(output + "/owner.json"));
    await context.addCookies([{ name: "locale", value: "zh-CN", url: base }]);
    await page.goto(base + "/login");
    await page.locator("#email").fill(account.email);
    await page.locator("#password").fill(account.password);
    await page.locator("button[type=submit]").click();
    await page.waitForURL((u) => u.pathname === "/workspace");
    await page.goto(base + "/workspace?settings=memory");
    await page.locator("[data-testid~=memory-settings]").waitFor();
    for (let index = 0; index < 12; index++) {
      await page.keyboard.press("Tab");
      assert(
        await page.evaluate(
          () => !!document.activeElement?.closest('[role="dialog"]'),
        ),
      );
    }
    checks.push("settings_keyboard_focus_stays_in_modal");
    await openProfile(page);
    await page.getByLabel("希望我怎么称呼你", { exact: true }).fill("视觉验收");
    await page.getByLabel("时区", { exact: true }).fill("Invalid/Zone");
    await page
      .getByRole("button", { name: "保存个人设置", exact: true })
      .click();
    await page
      .getByText("设置未保存。请检查时区或刷新后重试。", { exact: true })
      .waitFor();
    checks.push("inline_invalid_timezone_error");
    await page.screenshot({
      path: output + "/state-invalid-form.png",
      fullPage: true,
    });
    await page.getByLabel("时区", { exact: true }).fill("America/Los_Angeles");
    await page.getByLabel("回答时使用已有记忆", { exact: true }).check();
    let response = page.waitForResponse(
      (r) =>
        r.request().method() === "PATCH" &&
        r.url().endsWith("/api/me/personal-profile"),
    );
    await page
      .getByRole("button", { name: "保存个人设置", exact: true })
      .click();
    assert.equal((await response).status(), 200);
    checks.push("profile_saved_through_real_go");
    const value = "合成验收记录：使用简洁中文。";
    await page.locator("[data-testid~=memory-content]").fill(value);
    response = page.waitForResponse(
      (r) =>
        r.request().method() === "POST" && r.url().endsWith("/api/me/memories"),
    );
    await page.getByRole("button", { name: "保存记忆", exact: true }).click();
    assert.equal((await response).status(), 202);
    await page
      .locator("[data-testid~=memory-list] p", { hasText: value })
      .waitFor();
    checks.push("memory_create_visible");
    await page.getByLabel("搜索记忆", { exact: true }).fill("不存在的合成词");
    await page.getByRole("button", { name: "搜索", exact: true }).click();
    await page.getByText("没有匹配的记忆。", { exact: true }).waitFor();
    checks.push("memory_search_empty_state");
    await page.getByLabel("搜索记忆", { exact: true }).fill("");
    await page.getByRole("button", { name: "搜索", exact: true }).click();
    await page
      .locator("[data-testid~=memory-list] p", { hasText: value })
      .waitFor();
    await memoryAction(
      page,
      page.locator("[data-testid~=memory-list]>li").filter({ hasText: value }),
      "纠正",
    );
    const corrected = "合成验收记录：内容已纠正。";
    await page.locator("[data-testid~=memory-content]").fill(corrected);
    await page.getByRole("button", { name: "保存记忆", exact: true }).click();
    await page
      .locator("[data-testid~=memory-list] p", { hasText: corrected })
      .waitFor();
    checks.push("memory_correction_visible");
    await page.screenshot({
      path: output + "/state-memory-saved.png",
      fullPage: true,
    });
    await page.getByLabel("回答时使用已有记忆", { exact: true }).uncheck();
    response = page.waitForResponse(
      (r) =>
        r.request().method() === "PATCH" &&
        r.url().endsWith("/api/me/personal-profile"),
    );
    await page
      .getByRole("button", { name: "保存个人设置", exact: true })
      .click();
    assert.equal((await response).status(), 200);
    await memoryAction(
      page,
      page
        .locator("[data-testid~=memory-list]>li")
        .filter({ hasText: corrected }),
      "忘记",
    );
    await page
      .locator("[data-testid~=memory-list] p", { hasText: corrected })
      .waitFor({ state: "hidden" });
    checks.push("forget_remains_usable_after_memory_disabled");
    await page.keyboard.press("Escape");
    for (const mode of ["loading", "empty", "error"]) {
      const pattern = "**/api/threads/visual-thread/mcp-tasks?*";
      let release;
      const blocked=new Promise(resolve=>{release=resolve;});
      await page.route(pattern, async (route) => {
        if (mode === "loading") await blocked;
        await route.fulfill({
          status: mode === "error" ? 503 : 200,
          contentType: "application/json",
          body:
            mode === "error"
              ? JSON.stringify({ detail: "Synthetic failure" })
              : "[]",
        });
      });
      await page.goto(base + "/workspace/work");
      if (mode === "loading")
        await page.getByTestId("native-work").getByRole("status", { name: "正在读取工作…" }).waitFor();
      else if (mode === "empty")
        await page
          .getByText("这里暂时没有执行记录。回到助手，交代想做的事就好。", {
            exact: true,
          })
          .waitFor();
      else
        await page
          .getByRole("alert")
          .filter({ hasText: "有些记录暂时没读到" })
          .waitFor();
      checks.push("task_" + mode + "_state");
      await page.screenshot({
        path: output + `/state-tasks-${mode}.png`,
        fullPage: true,
      });
      release();
      await page.unroute(pattern);
    }
    await page.goto(base + "/workspace/work");
    await page.locator("[data-testid=work-record-row]").first().waitFor();
    for (const status of [
      "completed",
      "failed",
      "working",
      "input_required",
      "submitted",
      "cancelled",
    ]) {
      const opener = page
        .locator("[data-testid=work-record-row]", {
          hasText: "合成验收 · " + status + " ·",
        })
        .getByRole("button", { name: "查看详情", exact: true });
      await opener.click();
      await page.locator("[data-testid=task-detail]").waitFor();
      await page.screenshot({
        path: output + `/state-detail-${status}.png`,
        fullPage: true,
      });
      await page.keyboard.press("Escape");
      await inspector(page).waitFor({ state: "hidden" });
      assert(await opener.evaluate((e) => e === document.activeElement));
      checks.push("detail_" + status + "_and_focus_restore");
    }
    assert.equal(runs, 0);
    assert.deepEqual(errors, []);
    fs.writeFileSync(
      output + "/states.json",
      JSON.stringify(
        {
          checks,
          errors,
          runAttempts: runs,
          scope:
            "Real Go profile/memory admission and browser UI; synthetic memory provider/runtime; no model or Native calls.",
        },
        null,
        2,
      ),
    );
    console.log(`PASS ${checks.length} interactive state checks`);
    await context.close();
  } finally {
    await browser.close();
  }
})().catch((e) => {
  console.error(e);
  process.exit(1);
});
