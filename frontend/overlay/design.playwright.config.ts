import path from "node:path";

import { defineConfig } from "@playwright/test";
const output = process.env.DEERMATE_OUTPUT;
if (!output) throw new Error("Set a private DEERMATE_OUTPUT directory");
export default defineConfig({
  testDir: "tests/e2e/design",
  fullyParallel: false,
  workers: 1,
  outputDir: path.join(output, "browser-results"),
  snapshotPathTemplate: path.join(
    output,
    "gallery-baselines/{testFilePath}/{arg}{ext}",
  ),
  use: {
    baseURL: process.env.DEERMATE_URL,
    locale: "en-US",
    contextOptions: { reducedMotion: "reduce" },
    launchOptions: { executablePath: process.env.DEERMATE_BROWSER_EXECUTABLE },
  },
  reporter: "list",
});
