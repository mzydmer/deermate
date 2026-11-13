/* Explicit opt-in local Fake-model acceptance through the actual chat composer. */
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const crypto = require("node:crypto");
const { chromium } = require(
  process.env.DEERMATE_PLAYWRIGHT_MODULE ?? "playwright-core",
);
const output = process.env.DEERMATE_OUTPUT;

async function main() {
  const base = process.env.DEERMATE_URL;
  const url = new URL(base);
  assert(
    ["localhost", "127.0.0.1"].includes(url.hostname) &&
      ["http:", "https:"].includes(url.protocol),
  );
  assert(
    !url.username && !url.password && output && process.env.DEERMATE_OWNER_FILE,
  );
  assert.equal(process.env.DEERMATE_CAPTURE_FIXTURE, "1");
  fs.mkdirSync(output, { recursive: true, mode: 0o700 });
  const account = JSON.parse(
    fs.readFileSync(process.env.DEERMATE_OWNER_FILE, "utf8"),
  );
  assert.equal(
    account.synthetic_owner,
    true,
    "Use only a fresh synthetic owner",
  );
  const browser = await chromium.launch({
    headless: true,
    executablePath: process.env.DEERMATE_BROWSER_EXECUTABLE,
  });
  try {
    const context = await browser.newContext({
      locale: "zh-CN",
      viewport: { width: 1440, height: 1080 },
    });
    const page = await context.newPage();
    const errors = [];
    page.on("pageerror", (error) => errors.push(error.message));
    if ((await (await page.request.get(base + "/api/v1/auth/setup-status")).json()).needs_setup) {
      assert.equal((await page.request.post(base + "/api/v1/auth/initialize", { data: { email: account.email, password: account.password } })).status(), 201);
    }
    await page.goto(base + "/login");
    await page.locator("#email").fill(account.email);
    await page.locator("#password").fill(account.password);
    await page.locator('button[type="submit"]').click();
    await page.waitForURL((u) => u.pathname === "/workspace");
    const catalog = await (await page.request.get(base + "/api/models")).json();
    assert.equal(catalog.models.length, 1);
    assert.equal(catalog.models[0].name, "capture-fixture");
    const profile = await (
      await page.request.get(base + "/api/me/personal-profile")
    ).json();
    assert(profile.memory_enabled && profile.auto_capture_enabled);
    const csrf = (await context.cookies()).find(
      (cookie) => cookie.name === "csrf_token",
    ).value;
    const headers = {
      "X-CSRF-Token": csrf,
      "X-Expected-User-Id": profile.owner,
    };
    const thread = "sdk-memory-" + crypto.randomUUID();
    assert.equal(
      (
        await page.request.post(base + "/api/threads", {
          headers,
          data: { thread_id: thread },
        })
      ).status(),
      200,
    );
    await page.goto(base + "/workspace/chats/" + thread);
    const input = page.locator('textarea[name="message"]');
    await input.waitFor();
    const turns = [];
    const directive =
      "请记住：我偏好先看结论再看细节，合成标记 " +
      crypto.randomBytes(6).toString("hex") +
      "。";
    for (const text of ["你好，请简短回答。", directive]) {
      const pending = page.waitForResponse(
        (response) =>
          response.request().method() === "POST" &&
          /\/runs\/stream$/.test(new URL(response.url()).pathname),
        { timeout: 45000 },
      );
      await input.fill(text);
      await input.press("Enter");
      const response = await pending;
      assert.equal(response.status(), 200);
      const body = response.request().postDataJSON();
      const location = response.headers()["content-location"];
      assert(location);
      const run = location.split("/").pop();
      const deadline = Date.now() + 45000;
      let state;
      do {
        state = (
          await (
            await page.request.get(base + `/api/threads/${thread}/runs/${run}`)
          ).json()
        ).status;
        if (!["pending", "running"].includes(state)) break;
        await page.waitForTimeout(200);
      } while (Date.now() < deadline);
      assert.equal(state, "success");
      turns.push({
        status: response.status(),
        terminal_status: state,
        capture: response.headers()["x-deermate-memory-status"] ?? null,
        request_fields: Object.keys(body).sort(),
      });
      await page.waitForFunction(
        () => !document.querySelector('textarea[name="message"]')?.disabled,
      );
    }
    assert.equal(turns[0].capture, null);
    assert.equal(turns[1].capture, "queued");
    const deadline = Date.now() + 15000;
    let fact;
    do {
      const items = (
        await (await page.request.get(base + "/api/me/memories")).json()
      ).items;
      fact = items.find((item) => item.source?.thread_id === thread);
      if (fact) break;
      await page.waitForTimeout(200);
    } while (Date.now() < deadline);
    assert(fact && directive.endsWith(fact.content));
    assert.equal(
      (
        await page.request.delete(base + `/api/threads/${thread}`, { headers })
      ).status(),
      200,
    );
    const deletion = await page.request.delete(
      base + "/api/me/memories/" + fact.id,
      {
        headers,
        data: {
          operation_id: "sdk-forget-" + crypto.randomUUID(),
          expected_revision: fact.revision,
        },
      },
    );
    assert.equal(deletion.status(), 202);
    assert.deepEqual(errors, []);
    fs.writeFileSync(
      path.join(output, "receipt.json"),
      JSON.stringify(
        {
          passed: true,
          turns,
          checks: [
            "actual_composer_and_sdk_two_turns_succeed",
            "ordinary_question_not_captured",
            "second_turn_explicit_request_captured",
            "canonical_fact_has_current_chat_source",
            "synthetic_thread_and_fact_cleanup_admitted",
          ],
          page_errors: errors,
          synthetic_data_only: true,
          configured_cloud_models: 0,
          native_tasks: 0,
        },
        null,
        2,
      ) + "\n",
    );
    console.log(JSON.stringify({ passed: true, typed_turns: turns.length }));
  } finally {
    await browser.close();
  }
}

main().catch((error) => {
  if (output) {
    fs.mkdirSync(output, { recursive: true, mode: 0o700 });
    fs.writeFileSync(
      path.join(output, "error.txt"),
      error.stack ?? String(error),
      { mode: 0o600 },
    );
  }
  console.error(
    "Memory SDK acceptance failed; inspect its private output directory.",
  );
  process.exitCode = 1;
});
