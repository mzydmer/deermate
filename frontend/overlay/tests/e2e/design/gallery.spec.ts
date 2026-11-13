import fs from "node:fs";

import { expect, test } from "@playwright/test";
const base = process.env.DEERMATE_URL;
if (!base || !["localhost", "127.0.0.1"].includes(new URL(base).hostname))
  throw new Error("Gallery tests require the loopback synthetic fixture");
const owner = JSON.parse(
  fs.readFileSync(process.env.DEERMATE_OWNER_FILE!, "utf8"),
) as { email: string; password: string };
for (const width of [390, 768, 1024, 1280, 1440])
  for (const theme of ["light", "dark"]) {
    test(`gallery ${width} ${theme}`, async ({ page, context }) => {
      const response = await page.request.get("/__visual-fixture");
      expect((await response.json()).data).toBe("synthetic");
      await page.clock.setFixedTime(new Date("2026-11-12T12:00:00Z"));
      await context.addCookies([{ name: "locale", value: "en-US", url: base }]);
      await page.setViewportSize({ width, height: 900 });
      await page.goto("/login");
      await page.getByLabel("Email", { exact: true }).fill(owner.email);
      await page.getByLabel("Password", { exact: true }).fill(owner.password);
      await page.locator('button[type="submit"]').click();
      await page.waitForURL((url) => url.pathname === "/workspace");
      await page.evaluate(
        (value) => localStorage.setItem("theme", value),
        theme,
      );
      await page.goto("/workspace/design");
      await expect(page.getByTestId("design-gallery")).toBeVisible();
      await expect
        .poll(() =>
          page.evaluate(
            () => document.documentElement.scrollWidth <= innerWidth,
          ),
        )
        .toBe(true);
      await expect(page).toHaveScreenshot(`gallery-${width}-${theme}.png`, {
        fullPage: true,
        animations: "disabled",
      });
    });
  }
