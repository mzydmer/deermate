/* Capture the real UI with an isolated demo account. Never use production data.
   Requires a loopback synthetic administrator and a running Workspace v2 build. */
const fs = require("fs");
const path = require("path");
const assert = require("assert/strict");
const crypto = require("crypto");
const { chromium, request } = require(
  process.env.DEERMATE_PLAYWRIGHT_MODULE || "playwright",
);
const root = path.resolve(__dirname, "..");
const base = process.env.DEERMATE_MEDIA_URL;
const adminFile = process.env.DEERMATE_MEDIA_ADMIN;
assert(base && ["localhost", "127.0.0.1"].includes(new URL(base).hostname));
const admin = JSON.parse(fs.readFileSync(adminFile));
assert(admin.synthetic_owner === true && admin.origin === base);
const work = path.join(root, ".deermate", "readme-media");
const assets = path.join(root, "docs", "assets", "readme");
fs.mkdirSync(work, { recursive: true, mode: 0o700 });
fs.mkdirSync(assets, { recursive: true });
const captureFile = path.join(work, "capture.json");
if (fs.existsSync(captureFile))
  fs.renameSync(captureFile, path.join(work, "capture.previous.json"));
function save(file, value) {
  fs.writeFileSync(file, JSON.stringify(value, null, 2) + "\n", {
    mode: 0o600,
  });
}

let cleanup = async () => {};
(async () => {
  let control = await request.newContext({ baseURL: base });
  const login = await control.post("/api/v1/auth/login/local", {
    form: { username: admin.email, password: admin.password },
  });
  assert.equal(login.status(), 200);
  const original = await (await control.get("/api/v1/auth/me")).json();
  let cookies = (await control.storageState()).cookies;
  const controlLogin = control;
  control = await request.newContext({
    baseURL: base,
    storageState: await controlLogin.storageState(),
    extraHTTPHeaders: {
      "X-CSRF-Token": cookies.find((c) => c.name === "csrf_token").value,
      "X-Expected-User-Id": original.id,
    },
  });
  await controlLogin.dispose();
  const inventory = await (
    await control.get("/api/agent-authorizations")
  ).json();
  assert(
    inventory.devices.length === 0 && inventory.grants.length === 0,
    "Use a fresh synthetic media instance without enrolled devices.",
  );
  const accountFile = path.join(work, "account.json");
  let account = fs.existsSync(accountFile)
    ? JSON.parse(fs.readFileSync(accountFile))
    : null;
  if (!account) {
    account = {
      email: `readme-${crypto.randomUUID()}@example.com`,
      password: crypto.randomBytes(24).toString("base64url"),
      synthetic_owner: true,
      origin: base,
    };
    save(accountFile, account);
  }
  assert(
    account.synthetic_owner === true &&
      account.origin === base &&
      account.email.endsWith("@example.com"),
  );
  // Reconcile this unique address after an interrupted response; never create a replacement.
  const users = await (await control.get("/api/v1/admin/users")).json();
  const entries = Array.isArray(users) ? users : users.users;
  let demo = entries.find((u) => u.email === account.email);
  if (!demo) {
    const response = await control.post("/api/v1/admin/users", {
      data: {
        email: account.email,
        password: account.password,
        system_role: "admin",
      },
    });
    assert.equal(response.status(), 201);
    demo = await response.json();
  } else if (demo.disabled) {
    assert.equal(
      (
        await control.patch("/api/v1/admin/users/" + demo.id, {
          data: { disabled: false },
        })
      ).status(),
      200,
    );
  }
  account.id = demo.id;
  save(accountFile, account);
  cleanup = async () => {
    assert.equal(
      (
        await control.patch("/api/v1/admin/users/" + demo.id, {
          data: { disabled: true },
        })
      ).status(),
      200,
    );
    await control.dispose();
  };
  if (demo.system_role !== "admin") {
    assert.equal(
      (
        await control.patch("/api/v1/admin/users/" + demo.id, {
          data: { system_role: "admin" },
        })
      ).status(),
      200,
    );
  }
  let client = await request.newContext({ baseURL: base });
  assert.equal(
    (
      await client.post("/api/v1/auth/login/local", {
        form: { username: account.email, password: account.password },
      })
    ).status(),
    200,
  );
  cookies = (await client.storageState()).cookies;
  const clientLogin = client;
  client = await request.newContext({
    baseURL: base,
    storageState: await clientLogin.storageState(),
    extraHTTPHeaders: {
      "X-CSRF-Token": cookies.find((c) => c.name === "csrf_token").value,
      "X-Expected-User-Id": demo.id,
    },
  });
  await clientLogin.dispose();
  async function api(method, url, data) {
    assert(
      url.startsWith("/api/me/") ||
        url === "/api/threads" ||
        url.startsWith("/api/threads/"),
    );
    const r = await client.fetch(url, { method, ...(data ? { data } : {}) });
    if (!r.ok()) {
      const e = await r.json();
      throw new Error(
        `${method} ${url}: ${r.status()} ${e.code || JSON.stringify(e.detail)}`,
      );
    }
    return r.json();
  }
  const profile = await api("GET", "/api/me/personal-profile");
  await api("PATCH", "/api/me/personal-profile", {
    display_name: "Alex",
    timezone: "America/Los_Angeles",
    expected_revision: profile.revision,
  });
  const texts = [
    "Start with the answer, then the details.",
    "Keep research notes with their source links.",
    "I work on DeerMate, an open-source personal assistant.",
  ];
  let facts = (await api("GET", "/api/me/memories")).items;
  // These are actual manual memory writes. No generated conversation or execution results.
  for (let i = 0; i < texts.length; i++) {
    if (
      !facts.some((f) => f.content === texts[i]) &&
      !(
        i === 0 &&
        facts.some((f) => f.content.startsWith("Start with a short answer"))
      )
    ) {
      const op = await api("POST", "/api/me/memories", {
        operation_id: "readme-seed-" + i,
        content: texts[i],
        category: "preference",
        expected_revision: 0,
      });
      for (let n = 0; n < 60; n++) {
        const v = await api("GET", "/api/me/memory-operations/" + op.id);
        if (v.status === "completed") break;
        assert(!["failed", "invalidated"].includes(v.status));
        await new Promise((r) => setTimeout(r, 300));
      }
    }
  }
  facts = (await api("GET", "/api/me/memories")).items;
  assert(facts.length === 3);
  const thread = "readme-" + demo.id;
  await api("POST", "/api/threads", { thread_id: thread });
  await api("POST", "/api/threads/" + thread + "/state", {
    values: { title: "Prepare the next release" },
  });
  if (
    !(await api("GET", "/api/me/attention-topics")).items.some(
      (t) => t.thread_id === thread,
    )
  ) {
    await api("POST", "/api/me/attention-topics", {
      operation_id: "readme-focus",
      thread_id: thread,
      title: "Prepare the next release",
      goal: "Keep the launch notes clear and current.",
      priority: 1,
    });
  }
  const browser = await chromium.launch({
    headless: true,
    executablePath: process.env.DEERMATE_BROWSER_EXECUTABLE,
  });
  const context = await browser.newContext({
    storageState: await client.storageState(),
    viewport: { width: 1600, height: 1000 },
    locale: "en-US",
    colorScheme: "light",
    reducedMotion: "reduce",
    recordVideo: {
      dir: path.join(work, "raw"),
      size: { width: 1600, height: 1000 },
    },
  });
  await context.addCookies([{ name: "locale", value: "en-US", url: base }]);
  await context.addInitScript(() => localStorage.setItem("theme", "light"));
  let modelSubmissions = 0;
  await context.route("**/*", async (route) => {
    const r = route.request(),
      u = new URL(r.url());
    if (["http:", "https:"].includes(u.protocol) && u.origin !== base)
      return route.abort();
    if (
      r.method() === "POST" &&
      (/\/runs(?:\/|$)/.test(u.pathname) ||
        u.pathname === "/api/me/router/messages")
    ) {
      modelSubmissions++;
      return route.abort();
    }
    await route.continue();
  });
  const page = await context.newPage(),
    errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  const start = Date.now(),
    chapters = [];
  async function stamp(title) {
    chapters.push({ title, seconds: (Date.now() - start) / 1000 });
    await page.evaluate((title) => {
      let el = document.getElementById("readme-editorial-caption");
      if (!el) {
        el = document.createElement("aside");
        el.id = "readme-editorial-caption";
        document.body.append(el);
      }
      el.style.cssText =
        "position:fixed;bottom:0;left:0;right:0;height:40px;z-index:10000;display:flex;align-items:center;justify-content:space-between;padding:0 24px;background:var(--ds-colors-canvas);border-top:1px solid var(--ds-colors-hairline);font:500 12px system-ui;color:var(--ds-colors-body);pointer-events:none";
      el.replaceChildren();
      const a = document.createElement("span"),
        b = document.createElement("span");
      a.textContent = title;
      b.textContent = "Demo workspace · Real UI · No model or Native task runs";
      el.append(a, b);
    }, title);
  }
  try {
    await page.goto(base + "/workspace");
    await page.getByRole("heading", { name: /Alex/ }).waitFor();
    await page
      .getByText("Checking recent work…", { exact: true })
      .waitFor({ state: "hidden" });
    await page
      .getByText("Loading memory…", { exact: true })
      .waitFor({ state: "hidden" });
    await page.locator(".dm-focus-card").waitFor();
    await page.getByRole("button", { name: /A few things to pick up/ }).click();
    await stamp("01 / Your assistant, your recent work");
    await page.screenshot({ path: path.join(assets, "workspace.png") });
    await page.waitForTimeout(4500);
    await page
      .getByRole("link", { name: "About you", exact: true })
      .first()
      .click();
    await page
      .getByRole("heading", { name: "About you", exact: true })
      .waitFor();
    await page
      .getByRole("button", { name: "Correct", exact: true })
      .first()
      .waitFor();
    await stamp("02 / Review and correct what is remembered");
    const target = page
      .locator(".dm-memory-list>li")
      .filter({ hasText: "Start with" });
    await target.getByRole("button", { name: "Correct", exact: true }).click();
    const input = page.locator("#dm-memory-content");
    await input.scrollIntoViewIfNeeded();
    await page.waitForTimeout(1800);
    await input.fill("");
    await input.pressSequentially(
      "Start with a short answer. Add details when I ask.",
      { delay: 55 },
    );
    await page.waitForTimeout(1200);
    await page
      .getByRole("button", { name: "Save memory", exact: true })
      .click();
    await page.getByText("Memory updated.", { exact: true }).waitFor();
    await page.waitForTimeout(2600);
    await page
      .getByRole("link", { name: "Assistant", exact: true })
      .first()
      .click();
    await page.locator("#dm-assistant-message").waitFor();
    await page
      .getByText("Start with a short answer. Add details when I ask.", {
        exact: true,
      })
      .waitFor();
    await stamp("03 / Updated preferences, ready for the next chat");
    await page.waitForTimeout(3500);
    await page
      .getByRole("button", { name: "Temporary chat", exact: true })
      .click();
    await page.waitForURL((u) =>
      u.pathname.startsWith("/workspace/chats/temporary-"),
    );
    await page
      .getByText(
        "Temporary chat · No long-term memory is read or saved. Chat history is retained.",
        { exact: true },
      )
      .waitFor();
    await stamp("04 / A separate conversation without long-term memory");
    await page.waitForTimeout(4500);
    assert.equal(modelSubmissions, 0);
    assert.deepEqual(errors, []);
    const video = page.video();
    await context.close();
    await video.saveAs(path.join(work, "capture.webm"));
    const mobile = await browser.newContext({
      storageState: await client.storageState(),
      viewport: { width: 390, height: 844 },
      locale: "en-US",
      reducedMotion: "reduce",
    });
    await mobile.addCookies([{ name: "locale", value: "en-US", url: base }]);
    await mobile.addInitScript(() => localStorage.setItem("theme", "light"));
    const mp = await mobile.newPage();
    await mp.goto(base + "/workspace/memory");
    await mp
      .getByRole("button", { name: "Correct", exact: true })
      .first()
      .waitFor();
    await mp.screenshot({ path: path.join(assets, "memory-mobile.png") });
    await mobile.close();
    save(captureFile, {
      passed: true,
      synthetic_demo_account_disabled_after_capture: false,
      chapters,
      duration_seconds: (Date.now() - start) / 1000,
      model_submissions: modelSubmissions,
      page_errors: errors,
      synthetic_account: true,
      actual_ui_and_memory_writes: true,
      scope:
        "Local production UI, sample manual facts and one real followed topic. Memory correction persists through Go and DeerMem; empty temporary topic created. No model, Native run, or production account.",
    });
    console.log(
      JSON.stringify({
        passed: true,
        model_submissions: 0,
        chapters: chapters.length,
      }),
    );
  } finally {
    await browser.close();
    await client.dispose();
    // The outer cleanup disables only this dedicated synthetic account.
  }
})()
  .catch((e) => {
    console.error(e.message);
    process.exitCode = 1;
  })
  .finally(async () => {
    try {
      await cleanup();
      if (fs.existsSync(captureFile)) {
        const v = JSON.parse(fs.readFileSync(captureFile));
        v.synthetic_demo_account_disabled_after_capture = true;
        save(captureFile, v);
      }
    } catch {
      console.error("Synthetic demo account cleanup failed.");
      process.exitCode = 1;
    }
  });
