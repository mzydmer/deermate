/* Synthetic browser contracts for the component-driven workspace. */
const { waitForFocus } = require("./frontend_test_helpers.cjs");
const fs = require("node:fs");
const path = require("node:path");
const assert = require("node:assert/strict");
const { chromium } = require(
  process.env.DEERMATE_PLAYWRIGHT_MODULE || "playwright",
);
const base = process.env.DEERMATE_URL,
  output = process.env.DEERMATE_OUTPUT;
assert(
  base && output && ["127.0.0.1", "localhost"].includes(new URL(base).hostname),
);
const owner = JSON.parse(fs.readFileSync(process.env.DEERMATE_OWNER_FILE));
assert(
  owner.email === "visual-fixture@example.com" ||
    owner.synthetic_owner === true,
);
(async () => {
  fs.mkdirSync(output, { recursive: true, mode: 0o700 });
  const browser = await chromium.launch({
    headless: true,
    executablePath: process.env.DEERMATE_BROWSER_EXECUTABLE,
  });
  const checks = [],
    failures = [],
    errors = [];
  let submissions = 0;
  try {
    const auth = await browser.newContext({ locale: "en-US" });
    const p = await auth.newPage();
    p.setDefaultNavigationTimeout(120000);
    assert.equal(
      (await (await p.request.get(base + "/__visual-fixture")).json()).data,
      "synthetic",
    );
    if (
      (await (await p.request.get(base + "/api/v1/auth/setup-status")).json())
        .needs_setup
    )
      assert.equal(
        (
          await p.request.post(base + "/api/v1/auth/initialize", {
            data: { email: owner.email, password: owner.password },
          })
        ).status(),
        201,
      );
    await auth.clearCookies();
    await auth.addCookies([{ name: "locale", value: "en-US", url: base }]);
    await p.goto(base + "/login");
    await p.getByLabel("Email", { exact: true }).fill(owner.email);
    await p.getByLabel("Password", { exact: true }).fill(owner.password);
    await p.locator("button[type=submit]").click();
    await p.waitForURL((u) => u.pathname === "/workspace");
    const me = await (await p.request.get(base + "/api/v1/auth/me")).json();
    const csrf = (await auth.cookies()).find(
      (c) => c.name === "csrf_token",
    ).value;
    const temporary = await p.request.post(base + "/api/me/temporary-topics", {
      headers: { "X-CSRF-Token": csrf, "X-Expected-User-Id": me.id },
      data: { operation_id: require("node:crypto").randomUUID() },
    });
    assert.equal(temporary.status(), 200);
    const temporaryThread = (await temporary.json()).thread_id;
    assert(temporaryThread);
    assert.equal(
      (
        await (
          await p.request.get(base + "/api/me/topic-memory/" + temporaryThread)
        ).json()
      ).mode,
      "temporary",
    );
    const storage = await auth.storageState();
    await auth.close();
    checks.push("real_go_login");
    async function check(name, page, fn, meta = {}) {
      try {
        await fn();
        checks.push({ name, ...meta });
      } catch (e) {
        failures.push({
          name,
          ...meta,
          error: String(e.message).slice(0, 600),
        });
        await page
          .screenshot({
            path: path.join(
              output,
              `FAIL-${name}-${meta.width || "flow"}-${meta.theme || ""}.png`,
            ),
            fullPage: true,
          })
          .catch(() => {});
        console.log(
          "FAIL",
          name,
          meta.width || "",
          String(e.message).slice(0, 220),
        );
      }
    }
    async function geometry(page) {
      assert(
        await page.evaluate(
          () => document.documentElement.scrollWidth <= innerWidth,
        ),
        "document overflow",
      );
      const clipped = await page
        .locator(
          '[data-slot="dm-app-shell"], [data-slot="dm-app-shell"] > main',
        )
        .evaluateAll((nodes) =>
          nodes
            .filter((e) => e.scrollWidth > e.clientWidth + 1)
            .map((e) => ({
              slot: e.getAttribute("data-slot"),
              test: e.getAttribute("data-testid"),
              width: e.clientWidth,
              scroll: e.scrollWidth,
            })),
        );
      assert.deepEqual(clipped, [], "workspace container overflow");
    }
    async function contrast(page) {
      const result = await page.evaluate(() => {
        const canvas = document.createElement("canvas");
        canvas.width = canvas.height = 1;
        const ctx = canvas.getContext("2d", { willReadFrequently: true });
        function rgba(value) {
          ctx.clearRect(0, 0, 1, 1);
          ctx.fillStyle = value;
          ctx.fillRect(0, 0, 1, 1);
          return Array.from(ctx.getImageData(0, 0, 1, 1).data).map((v, i) =>
            i === 3 ? v / 255 : v / 255,
          );
        }
        function over(top, bottom) {
          return [0, 1, 2]
            .map((i) => top[i] * top[3] + bottom[i] * (1 - top[3]))
            .concat(1);
        }
        function light(c) {
          return c
            .slice(0, 3)
            .map((v) =>
              v <= 0.04045 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4,
            )
            .reduce((s, v, i) => s + v * [0.2126, 0.7152, 0.0722][i], 0);
        }
        const bad = [];
        let count = 0;
        for (const el of document.querySelectorAll(
          "[data-slot=dm-text],[data-slot=dm-badge],a,p,caption",
        )) {
          const box = el.getBoundingClientRect();
          if (
            !el.textContent.trim() ||
            !box.width ||
            !box.height ||
            el.closest("[disabled],[aria-disabled=true],[aria-hidden=true]")
          )
            continue;
          const style = getComputedStyle(el);
          if (style.visibility === "hidden" || style.opacity === "0") continue;
          const parents = [];
          let node = el;
          while (node) {
            parents.push(node);
            node = node.parentElement;
          }
          let bg = [1, 1, 1, 1];
          for (const parent of parents.reverse())
            bg = over(rgba(getComputedStyle(parent).backgroundColor), bg);
          const fg = over(rgba(style.color), bg);
          const ratio =
            (Math.max(light(bg), light(fg)) + 0.05) /
            (Math.min(light(bg), light(fg)) + 0.05);
          count++;
          if (ratio < 4.5)
            bad.push({
              text: el.textContent.trim().slice(0, 60),
              ratio,
              color: style.color,
            });
        }
        return { count, bad };
      });
      assert(result.count > 0);
      assert.deepEqual(result.bad, [], JSON.stringify(result.bad));
    }
    for (const width of [390, 768, 1024, 1280, 1440])
      for (const theme of ["light", "dark"]) {
        const context = await browser.newContext({
          storageState: storage,
          locale: "en-US",
          viewport: { width, height: 900 },
          reducedMotion: "reduce",
          colorScheme: theme,
        });
        await context.addInitScript(
          (t) => localStorage.setItem("theme", t),
          theme,
        );
        const page = await context.newPage();
        page.setDefaultNavigationTimeout(120000);
        page.setDefaultTimeout(15000);
        page.on("pageerror", (e) =>
          errors.push({ width, theme, message: e.message }),
        );
        await page.route("**/api/**", async (route) => {
          if (
            route.request().method() === "POST" &&
            /\/runs(?:\/|$)/.test(new URL(route.request().url()).pathname)
          ) {
            submissions++;
            await route.abort();
          } else await route.continue();
        });
        const meta = { width, theme };
        for (const [name, route] of [
          ["home", "/workspace"],
          ["work", "/workspace/work"],
          ["memory", "/workspace/memory"],
          ["chat", "/workspace/chats/new"],
          ["chat-existing", "/workspace/chats/" + temporaryThread],
          ["docs", "/docs"],
          ["article", "/docs/guide/quickstart"],
          ["admin", "/admin"],
          ["grants", "/admin/agents"],
        ])
          await check(
            name,
            page,
            async () => {
              const historyResponse =
                name === "chat-existing"
                  ? page.waitForResponse((r) =>
                      new URL(r.url()).pathname.endsWith(
                        "/" + temporaryThread + "/messages/page",
                      ),
                    )
                  : null;
              await page.goto(base + route);
              if (historyResponse) {
                const response = await historyResponse;
                assert.equal(response.status(), 200);
                assert.deepEqual(await response.json(), {
                  data: [],
                  has_more: false,
                  next_before_seq: null,
                });
              }
              if (name === "home")
                await page.getByTestId("message-input").waitFor();
              if (name === "work")
                await page.getByTestId("work-record-row").first().waitFor();
              if (name === "memory")
                await page.getByTestId("memory-content").waitFor();
              if (name.startsWith("chat"))
                await page.locator("textarea[name=message]").waitFor();
              await page.waitForTimeout(250);
              await geometry(page);
              await contrast(page);
              if (
                ["home", "work", "memory", "chat", "chat-existing"].includes(
                  name,
                )
              ) {
                const side = page.locator("[data-sidebar=sidebar]").first();
                if (width < 600)
                  assert.equal(
                    await side.count(),
                    0,
                    "mobile starts with a drawer",
                  );
                else {
                  const box = await page
                    .locator("[data-slot=sidebar-container]")
                    .boundingBox();
                  assert.equal(Math.round(box.width), width < 960 ? 64 : 240);
                }
              }
              if (name === "home" || name.startsWith("chat")) {
                const input =
                  name === "home"
                    ? page.getByTestId("message-input")
                    : page.locator("textarea[name=message]");
                assert(await input.isVisible());
                const send = page.getByRole("button", {
                  name: "Send",
                  exact: true,
                });
                if (name.startsWith("chat")) {
                  assert(await send.isDisabled(), "empty chat cannot submit");
                  const shape = await send.evaluate((e) => ({
                    width: e.getBoundingClientRect().width,
                    height: e.getBoundingClientRect().height,
                    radius: parseFloat(getComputedStyle(e).borderRadius),
                  }));
                  assert.equal(shape.width, shape.height);
                  assert(
                    shape.radius >= shape.width / 2,
                    "send stays circular",
                  );
                }
                if (name.startsWith("chat"))
                  assert.equal(
                    Math.round(
                      (await page.getByTestId("chat-topbar").boundingBox())
                        .height,
                    ),
                    64,
                  );

                const heading = page.getByRole("heading", { level: 1 }).first();
                if (await heading.count()) {
                  const box = await heading.boundingBox();
                  assert(
                    box.y >= 0 && box.y + box.height <= 900,
                    "heading must remain visible above composer",
                  );
                }

                async function checkComposerFooter() {
                  if (name !== "chat-existing") return;
                  await page
                    .getByTestId("chat-memory-banner")
                    .getByRole("status")
                    .waitFor();
                  assert(
                    await page.evaluate(
                      () =>
                        document.documentElement.scrollHeight <= innerHeight,
                    ),
                    "temporary banner must not push the composer below viewport",
                  );
                  const footer = page.getByText(
                    "DeerFlow is AI and can make mistakes",
                    { exact: true },
                  );
                  const bounds = await footer.boundingBox();
                  const form = await input
                    .locator("xpath=ancestor::form")
                    .boundingBox();
                  assert(
                    bounds && form,
                    "conversation composer and disclaimer visible",
                  );
                  assert(
                    bounds.y >= form.y + form.height + 7.9,
                    "disclaimer has normal-flow spacing below input",
                  );
                  assert(
                    bounds.y + bounds.height <= 900 - 15.9,
                    "whole disclaimer has bottom breathing room",
                  );
                  assert(
                    form.y >= 64 && form.y + form.height < 900,
                    "composer remains in viewport",
                  );
                  assert.equal(
                    await footer.evaluate((e) => getComputedStyle(e).position),
                    "static",
                  );
                }
                await checkComposerFooter();
                assert.equal(
                  await input.evaluate((e) => getComputedStyle(e).resize),
                  "none",
                );
                await input.fill(
                  ("Long synthetic draft / path_".repeat(40) + "\n").repeat(8),
                );
                assert(
                  await input.evaluate((e) => e.clientHeight < 400),
                  "composer bounded height",
                );
                if (name.startsWith("chat"))
                  assert(await send.isEnabled(), "draft enables submit");
                await checkComposerFooter();
                await input.fill("");
                if (name.startsWith("chat")) assert(await send.isDisabled());
              }
              if (width < 600) {
                const undersized = await page
                  .locator("button:visible")
                  .evaluateAll((nodes) =>
                    nodes
                      .filter(
                        (e) =>
                          !e.disabled &&
                          e.getAttribute("aria-hidden") !== "true" &&
                          e.getAttribute("data-slot") !== "dm-checkbox",
                      )
                      .filter((e) => {
                        const r = e.getBoundingClientRect();
                        return r.width < 43.9 || r.height < 43.9;
                      })
                      .map((e) => ({
                        label:
                          e.getAttribute("aria-label") ||
                          e.textContent.trim().slice(0, 40),
                        box: e.getBoundingClientRect().toJSON(),
                      })),
                  );
                assert.deepEqual(undersized, [], "mobile button targets");
              }
              await page.screenshot({
                path: path.join(output, `${name}-${width}-${theme}.png`),
                fullPage: true,
              });
            },
            meta,
          );
        await check(
          "inspector",
          page,
          async () => {
            await page.goto(base + "/workspace/work");
            const rows = page.getByTestId("work-record-row");
            await rows.first().waitFor();
            const heights = await rows.evaluateAll((nodes) =>
              nodes.map((e) => e.getBoundingClientRect().height),
            );
            assert(
              heights.every((h) => h >= 48 && h <= 64),
              JSON.stringify(heights),
            );
            const opener = rows
              .first()
              .getByRole("button", { name: "View details" });
            await opener.click();
            const panel = page.locator(
              "[data-slot=dm-inspector],[data-testid=pattern-inspector-sheet]",
            );
            await panel.waitFor();
            await page.getByTestId("task-detail").waitFor();
            assert.equal(
              await page.getByRole("dialog").count(),
              width < 1280 ? 1 : 0,
            );
            await panel
              .getByText("Validation passed", { exact: true })
              .waitFor();
            await panel
              .getByText("Deployment unconfirmed", { exact: true })
              .waitFor();
            await panel
              .getByRole("button", { name: "Test output", exact: true })
              .click();
            const viewport = panel
              .getByTestId("evidence-scroll")
              .first()
              .locator("[data-radix-scroll-area-viewport]");
            const bounds = await viewport.evaluate((e) => ({
              height: e.clientHeight,
              scroll: e.scrollHeight,
            }));
            assert(
              bounds.height <= 320 && bounds.scroll > bounds.height,
              JSON.stringify(bounds),
            );
            await panel
              .getByRole("button", { name: "Test output", exact: true })
              .click();
            if (width >= 1280) {
              await panel
                .getByRole("button", { name: "Expand details", exact: true })
                .click();
              await page.getByRole("dialog").waitFor();
              await page
                .getByRole("dialog")
                .getByRole("button", { name: "Dock details", exact: true })
                .click();
              await page.getByRole("dialog").waitFor({ state: "hidden" });
              await page.locator("[data-slot=dm-inspector]").waitFor();
            }
            await geometry(page);
            await page.screenshot({
              path: path.join(output, `inspector-${width}-${theme}.png`),
              fullPage: true,
            });
            await page.keyboard.press("Escape");
            await panel.waitFor({ state: "hidden" });
            await waitForFocus(page, opener);
          },
          meta,
        );
        await check(
          "gallery_keyboard",
          page,
          async () => {
            await page.goto(base + "/workspace/design");
            await page.getByTestId("design-gallery").waitFor();
            await geometry(page);
            await contrast(page);
            const open = page.getByRole("button", {
              name: "Open dialog",
              exact: true,
            });
            await open.click();
            await page.getByRole("dialog").waitFor();
            await page.keyboard.press("Escape");
            await page.getByRole("dialog").waitFor({ state: "hidden" });
            await waitForFocus(page, open);
            const menu = page.getByRole("button", {
              name: "Open menu",
              exact: true,
            });
            await menu.focus();
            await page.keyboard.press("Tab");
            await page.keyboard.press("Shift+Tab");
            assert.equal(
              await menu.evaluate((e) => getComputedStyle(e).outlineWidth),
              "2px",
            );
            await page.keyboard.press("ArrowDown");
            await page.getByRole("menu").waitFor();
            await page.keyboard.press("ArrowDown");
            assert.equal(
              await page.evaluate(() =>
                document.activeElement?.getAttribute("role"),
              ),
              "menuitem",
            );
            await page.keyboard.press("Escape");
            await page.getByRole("menu").waitFor({ state: "hidden" });
            await waitForFocus(page, menu);
            const moving = await page
              .locator("[data-slot=dm-spinner]")
              .evaluateAll((nodes) =>
                nodes.map((e) => getComputedStyle(e).animationName),
              );
            assert(moving.length > 0);
            assert(moving.every((v) => v === "none"));
          },
          meta,
        );
        if (width < 600)
          await check(
            "sidebar_keyboard",
            page,
            async () => {
              await page.goto(base + "/workspace");
              const trigger = page
                .getByTestId("topbar")
                .locator("[data-sidebar=trigger]");
              await trigger.click();
              const dialog = page.getByRole("dialog");
              await dialog.waitFor();
              const visited = new Set();
              for (let i = 0; i < 24; i++) {
                await page.keyboard.press("Tab");
                assert(
                  await page.evaluate(
                    () => !!document.activeElement.closest("[role=dialog]"),
                  ),
                );
                visited.add(
                  await page.evaluate(() =>
                    document.activeElement.getAttribute("href"),
                  ),
                );
              }
              for (const href of [
                "/workspace",
                "/workspace/work",
                "/workspace/memory",
                "/workspace/chats",
              ])
                assert(visited.has(href), `Tab reaches ${href}`);
              await page.keyboard.press("Escape");
              await dialog.waitFor({ state: "hidden" });
              await waitForFocus(page, trigger);
            },
            meta,
          );
        await context.close();
      }
    assert.equal(submissions, 0);
    fs.writeFileSync(
      path.join(output, "contracts.json"),
      JSON.stringify({ checks, failures, errors, submissions }, null, 2),
    );
    assert.deepEqual(errors, [], "browser errors");
    assert.deepEqual(failures, [], "contract failures");
    console.log(
      `PASS ${checks.length} contracts; five widths, two themes; no model submissions`,
    );
  } finally {
    await browser.close();
  }
})().catch((e) => {
  console.error(e);
  process.exit(1);
});
