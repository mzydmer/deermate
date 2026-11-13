const fs = require("fs");
const path = require("path");
const { chromium } = require(
  process.env.DEERMATE_PLAYWRIGHT_MODULE || "playwright",
);
(async () => {
  const root = path.resolve(__dirname, "..");
  const output = process.env.DEERMATE_OUTPUT;
  if (!output) throw new Error("Set a private DEERMATE_OUTPUT directory");
  fs.mkdirSync(output, { recursive: true, mode: 0o700 });
  const browser = await chromium.launch({
    ...(process.env.DEERMATE_BROWSER_EXECUTABLE
      ? { executablePath: process.env.DEERMATE_BROWSER_EXECUTABLE }
      : {}),
    headless: true,
  });
  const checks = [];
  for (const width of [390, 768, 1024, 1280, 1440])
    for (const dark of [false, true]) {
      const page = await browser.newPage({
        viewport: { width, height: 900 },
        reducedMotion: "reduce",
      });
      const css =
        fs.readFileSync(
          path.join(root, "frontend/overlay/src/styles/design-tokens.css"),
          "utf8",
        ) +
        "\n" +
        fs.readFileSync(
          path.join(root, "frontend/overlay/src/styles/design-components.css"),
          "utf8",
        ) +
        "\n" +
        fs.readFileSync(
          path.join(
            root,
            "frontend/overlay/src/components/deermate/ui/upstream.css",
          ),
          "utf8",
        );
      await page.setContent(
        `<html class="${dark ? "dark" : ""}" lang="zh-CN"><style>${css}</style><main><h1>组件验收</h1><button data-slot="button" data-variant="default">主要操作</button><input data-slot="input" aria-label="名称"><div class="ds-app-card">内容</div><div class="ds-app-badge" data-design-variant="success">已完成</div></main></html>`,
      );
      const values = await page.evaluate(() => {
        const button = document.querySelector("button"),
          input = document.querySelector("input"),
          card = document.querySelector(".ds-app-card");
        return {
          radius: getComputedStyle(button).borderRadius,
          height: button.getBoundingClientRect().height,
          inputHeight: input.getBoundingClientRect().height,
          background: getComputedStyle(button).backgroundColor,
          cardShadow: getComputedStyle(card).boxShadow,
          overflow: document.documentElement.scrollWidth > innerWidth,
          success: getComputedStyle(document.documentElement)
            .getPropertyValue("--dm-success")
            .trim(),
        };
      });
      if (
        values.radius !== "8px" ||
        values.height < 40 ||
        values.inputHeight < 40 ||
        values.cardShadow !== "none" ||
        values.overflow
      )
        throw Error(JSON.stringify({ width, dark, values }));
      await page.keyboard.press("Tab");
      const focus = await page
        .locator("button")
        .evaluate((e) => getComputedStyle(e).outlineStyle);
      if (focus !== "solid") throw Error("No visible keyboard focus");
      checks.push({
        surface: "shared-primitives",
        width,
        dark,
        values,
        keyboardFocus: true,
      });
      // Render the actual management HTML and actual CSS, with scripts disabled: visual shell only.
      for (const name of ["admin", "authorizations"]) {
        let html = fs
          .readFileSync(
            path.join(root, `backend/internal/controlplane/${name}.html`),
            "utf8",
          )
          .replace(/<script[\s\S]*?<\/script>/g, "")
          .replace(
            "/* DEERMATE_DESIGN_TOKENS */",
            fs.readFileSync(
              path.join(
                root,
                "backend/internal/controlplane/design-tokens.css",
              ),
              "utf8",
            ) +
              fs.readFileSync(
                path.join(
                  root,
                  "backend/internal/controlplane/design-components.css",
                ),
                "utf8",
              ),
          );
        await page.setContent(html);
        if (dark)
          await page.locator("html").evaluate((e) => e.classList.add("dark"));
        const overflow = await page.evaluate(
          () => document.documentElement.scrollWidth > innerWidth,
        );
        if (overflow) throw Error(`${name} overflow ${width}`);
        checks.push({
          surface: name,
          width,
          dark,
          overflow: false,
          scope: "actual HTML/CSS; scripts disabled, no account/API data",
        });
        if (width === 390 || width === 1440)
          await page.screenshot({
            path: path.join(
              output,
              `${name}-${width}-${dark ? "dark" : "light"}.png`,
            ),
            fullPage: true,
          });
      }
      // Mount the real non-React extension with deterministic offline callbacks.
      await page.setContent(
        `<html class="${dark ? "dark" : ""}" lang="en"><style>${css}</style><main id="tooling"></main></html>`,
      );
      const tooling = fs.readFileSync(
        path.join(root, "src/deermate/tooling_ui/index.mjs"),
        "utf8",
      );
      await page.evaluate(async (source) => {
        const module = await import(
          "data:text/javascript;base64," +
            btoa(unescape(encodeURIComponent(source)))
        );
        module.default.surfaces[0].mount(document.querySelector("#tooling"), {
          locale: "en-US",
          signal: new AbortController().signal,
          callBackend: async (operation) =>
            operation === "inventory"
              ? {
                  native: [
                    { name: "Synthetic public reader", status: "loaded" },
                    { name: "Synthetic unchecked tool", status: "unknown" },
                  ],
                  connections: [
                    {
                      name: "Synthetic connection / " + "long-name_".repeat(8),
                      scope: "personal",
                      enabled: true,
                    },
                    {
                      name: "Synthetic disabled connection",
                      scope: "personal",
                      enabled: false,
                    },
                  ],
                }
              : { status: "discovered", total: 2, tools: [] },
        });
      }, tooling);
      await page
        .getByRole("button", { name: "Refresh status", exact: true })
        .waitFor();
      await page.waitForFunction(
        () => !document.querySelector("#tooling button").disabled,
      );
      if (
        await page.evaluate(
          () => document.documentElement.scrollWidth > innerWidth,
        )
      )
        throw Error("Tooling overflow");
      await page
        .getByRole("button", { name: /Test connection Synthetic connection/ })
        .click();
      await page.getByText("Connected · 2 tools", { exact: true }).waitFor();
      if (
        !(await page
          .getByRole("button", {
            name: "Test connection Synthetic disabled connection",
            exact: true,
          })
          .isDisabled())
      )
        throw Error("Disabled connection became actionable");
      await page.screenshot({
        path: path.join(
          output,
          `tooling-${width}-${dark ? "dark" : "light"}.png`,
        ),
        fullPage: true,
      });
      checks.push({
        surface: "tooling-extension",
        width,
        dark,
        scope: "actual extension module; synthetic callbacks, no MCP discovery",
      });
      await page.close();
    }
  fs.writeFileSync(
    path.join(output, "browser.json"),
    JSON.stringify(
      {
        checks,
        passed: checks.length,
        scope:
          "Headless Chrome local shared primitives and actual Go HTML/CSS shells. No authenticated workflow or model call.",
      },
      null,
      2,
    ),
  );
  await browser.close();
  console.log(`PASS ${checks.length} theme/viewport checks`);
})().catch((e) => {
  console.error(e);
  process.exit(1);
});
