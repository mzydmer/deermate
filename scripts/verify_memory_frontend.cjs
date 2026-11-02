/* Local synthetic acceptance: real Go/API storage and UI, no Agent runs. */
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const crypto = require("node:crypto");
const { chromium } = require(process.env.DEERMATE_PLAYWRIGHT_MODULE ?? "playwright-core");

const output = process.env.DEERMATE_OUTPUT;

async function main() {
  const base = process.env.DEERMATE_URL;
  const url = new URL(base);
  assert(["localhost", "127.0.0.1"].includes(url.hostname) && ["http:", "https:"].includes(url.protocol));
  assert(!url.username && !url.password);
  assert(output && process.env.DEERMATE_OWNER_FILE);
  const account = JSON.parse(fs.readFileSync(process.env.DEERMATE_OWNER_FILE, "utf8"));
  fs.mkdirSync(output, { recursive: true, mode: 0o700 });
  const checks = [];
  const errors = [];
  const browser = await chromium.launch({
    headless: true, executablePath: process.env.DEERMATE_BROWSER_EXECUTABLE,
  });
  try {
    const context = await browser.newContext({ viewport: { width: 1440, height: 1080 }, locale: "zh-CN" });
    const page = await context.newPage();
    let agentRunRequests = 0;
    page.on("pageerror", (e) => errors.push(e.message));
    page.on("request", (request) => {
      if (request.method() === "POST" && /\/runs(?:\/|$)/.test(new URL(request.url()).pathname)) agentRunRequests++;
    });
    const init = await page.request.get(base + "/api/v1/auth/setup-status");
    if ((await init.json()).needs_setup) {
      const created = await page.request.post(base + "/api/v1/auth/initialize", { data: account });
      assert.equal(created.status(), 201);
    }
    await context.clearCookies();
    await context.addCookies([{ name: "locale", value: "zh-CN", url: base }]);

    async function login(who) {
      await page.goto(base + "/login");
      await page.locator("#email").fill(who.email);
      await page.locator("#password").fill(who.password);
      await page.locator('button[type="submit"]').click();
      await page.waitForURL((u) => u.pathname === "/workspace", { timeout: 45000 });
      await page.locator(".dm-desk").waitFor();
    }
    async function csrf() {
      return (await context.cookies()).find((c) => c.name === "csrf_token").value;
    }
    async function saveProfile() {
      const response = page.waitForResponse((r) => r.request().method() === "PATCH" && new URL(r.url()).pathname === "/api/me/personal-profile");
      await page.getByRole("button", { name: /^(保存个人设置|Save personal settings)$/ }).click();
      assert.equal((await response).status(), 200);
    }
    async function saveFact() {
      const response = page.waitForResponse((r) => ["POST", "PATCH"].includes(r.request().method()) && /^\/api\/me\/memories(?:\/mem_[a-f0-9]+)?$/.test(new URL(r.url()).pathname));
      await page.getByRole("button", { name: /^(保存记忆|Save memory)$/ }).click();
      assert.equal((await response).status(), 202);
    }

    await login(account);
    await page.locator(".dm-memory > summary").click();
    const name = page.getByLabel(/希望我怎么称呼你|What should I call/);
    await name.fill("记忆验收");
    await page.getByLabel(/^(时区|Timezone)$/).fill("Asia/Shanghai");
    const toggle = page.getByLabel(/^(开启个人记忆|Enable personal memory)$/);
    await toggle.check();
    await saveProfile();
    await page.getByRole("heading", { level: 1, name: /记忆验收/ }).waitFor();
    checks.push("real_login_profile_and_personal_greeting");
    const formStyle = await page.locator("#dm-memory-content").evaluate((element) => {
      const style = getComputedStyle(element);
      return { border: style.borderTopWidth, background: style.backgroundColor, token: style.getPropertyValue("--dm-background").trim() };
    });
    assert.equal(formStyle.border, "1px");
    assert.equal(formStyle.background, "rgb(255, 255, 255)");
    assert.match(formStyle.token, /^#(?:fff|ffffff)$/i);
    checks.push("canonical_design_tokens_and_visible_form_boundaries");

    const first = "合成验收偏好：请使用中文，先给结论。";
    const second = "合成验收偏好：回复可以使用简短列表。";
    await page.locator("#dm-memory-content").fill(first);
    await saveFact();
    await page.locator(".dm-memory-list p", { hasText: first }).waitFor();
    checks.push("explicit_fact_saved_and_listed");
    const search = page.getByLabel(/^(搜索记忆|Search memory)$/);
    await search.fill("结论");
    const query = page.waitForRequest((r) => new URL(r.url()).pathname === "/api/me/memories/search" && r.method() === "POST");
    await page.getByRole("button", { name: /^(搜索|Search)$/ }).click();
    const queryRequest = await query;
    assert.equal(queryRequest.postDataJSON().query, "结论");
    assert.equal(new URL(queryRequest.url()).search, "");
    await page.locator(".dm-memory-list p", { hasText: first }).waitFor();
    checks.push("chinese_search_uses_body_not_url");
    await search.fill("");
    await page.getByRole("button", { name: /^(搜索|Search)$/ }).click();
    await page.getByRole("button", { name: /^(纠正|Correct)$/ }).click();
    await page.locator("#dm-memory-content").fill(second);
    await saveFact();
    await page.locator(".dm-memory-list p", { hasText: second }).waitFor();
    assert.equal(await page.locator(".dm-memory-list p", { hasText: first }).count(), 0);
    checks.push("correction_replaces_visible_fact");

    await toggle.uncheck();
    await saveProfile();
    await page.waitForFunction(() => document.querySelector("#dm-memory-content")?.disabled);
    await page.locator(".dm-memory-list p", { hasText: second }).waitFor();
    checks.push("disabled_memory_keeps_management_and_blocks_new_save");
    const deletion = page.waitForResponse((r) => r.request().method() === "DELETE" && new URL(r.url()).pathname.startsWith("/api/me/memories/"));
    await page.getByRole("button", { name: /^(忘记|Forget)$/ }).click();
    assert.equal((await deletion).status(), 202);
    await page.locator(".dm-memory-list p", { hasText: second }).waitFor({ state: "detached" });
    assert.deepEqual((await (await page.request.get(base + "/api/me/memories")).json()).items, []);
    checks.push("forget_works_while_off_and_removes_fact");

    await toggle.check();
    await saveProfile();
    const privateMarker = "第一位合成用户的独有偏好，不应出现在另一账号。";
    await page.locator("#dm-memory-content").fill(privateMarker);
    await saveFact();
    await page.locator(".dm-memory-list p", { hasText: privateMarker }).waitFor();
    await page.locator(".dm-desk").evaluate((element) => { element.scrollTop = 0; });
    await page.screenshot({ path: path.join(output, "memory-desktop.png"), fullPage: true });
    await page.setViewportSize({ width: 390, height: 844 });
    assert(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth));
    await page.screenshot({ path: path.join(output, "memory-mobile.png"), fullPage: true });
    await page.emulateMedia({ colorScheme: "dark", reducedMotion: "reduce" });
    await page.waitForFunction(() => document.documentElement.classList.contains("dark"));
    assert.equal(await page.locator("#dm-memory-content").evaluate((element) => getComputedStyle(element).backgroundColor), "rgb(10, 10, 10)");
    await page.screenshot({ path: path.join(output, "memory-dark.png"), fullPage: true });
    checks.push("desktop_390px_dark_and_reduced_motion_layout");

    const other = { email: "memory-browser-second@example.com", password: crypto.randomBytes(24).toString("hex") };
    const created = await page.request.post(base + "/api/v1/admin/users", { data: { ...other, system_role: "user" }, headers: { "X-CSRF-Token": await csrf() } });
    assert.equal(created.status(), 201);
    const loggedOut = await page.request.post(base + "/api/v1/auth/logout", { headers: { "X-CSRF-Token": await csrf() } });
    assert.equal(loggedOut.status(), 200);
    await login(other);
    await page.locator(".dm-memory > summary").click();
    await page.getByLabel(/希望我怎么称呼你|What should I call/).waitFor();
    assert.equal(await page.getByLabel(/希望我怎么称呼你|What should I call/).inputValue(), "");
    assert.equal(await page.locator(".dm-memory-list p", { hasText: privateMarker }).count(), 0);
    assert.deepEqual((await (await page.request.get(base + "/api/me/memories")).json()).items, []);
    checks.push("account_switch_has_no_previous_name_or_fact");
    assert.deepEqual(errors, []);
    assert.equal(agentRunRequests, 0);
    fs.writeFileSync(path.join(output, "receipt.json"), JSON.stringify({ passed: true, checks, page_errors: errors, synthetic_data_only: true, browser_agent_run_requests: agentRunRequests, configured_cloud_models: 0 }, null, 2) + "\n");
    console.log(JSON.stringify({ passed: true, checks: checks.length }));
  } finally { await browser.close(); }
}

main().catch((error) => {
  if (output) { fs.mkdirSync(output, { recursive: true, mode: 0o700 }); fs.writeFileSync(path.join(output, "error.txt"), error.stack ?? String(error), { mode: 0o600 }); }
  console.error("Memory UI acceptance failed; inspect its private output directory.");
  process.exitCode = 1;
});
