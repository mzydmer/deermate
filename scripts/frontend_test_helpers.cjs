/* Shared semantic interactions; no selector depends on a visual recipe. */
async function memoryAction(page, row, name) {
  await row.getByRole("button", { name: /^(更多|More)$/ }).click();
  await page.getByRole("menuitem", { name, exact: true }).click();
  if (name === "忘记" || name === "Forget")
    await page
      .getByRole("dialog")
      .getByRole("button", { name, exact: true })
      .click();
}
async function chooseOption(page, control, value) {
  await control.click();
  await page.locator(`[role=option][data-value="${value}"]`).click();
}
function inspector(page) {
  return page.locator(
    '[data-slot="dm-inspector"], [data-testid="pattern-inspector-sheet"]',
  );
}
module.exports = { memoryAction, chooseOption, inspector };

async function openProfile(page) {
  const trigger = page.locator(
    "[data-testid~=memory-settings] > [data-slot=dm-disclosure-trigger]",
  );
  await trigger.waitFor();
  if ((await trigger.getAttribute("aria-expanded")) !== "true")
    await trigger.click();
}
module.exports.openProfile = openProfile;

async function seedMemory(page, context, base, content) {
  const user = await (await page.request.get(base + "/api/v1/auth/me")).json();
  const csrf = (await context.cookies()).find(
    (c) => c.name === "csrf_token",
  ).value;
  const response = await page.request.post(base + "/api/me/memories", {
    headers: { "X-CSRF-Token": csrf, "X-Expected-User-Id": user.id },
    data: {
      operation_id: require("node:crypto").randomUUID(),
      category: "context",
      content,
      expected_revision: 0,
    },
  });
  require("node:assert/strict").equal(response.status(), 202);
  const op = await response.json();
  const deadline = Date.now() + 15000;
  while (Date.now() < deadline) {
    const current = await (
      await page.request.get(base + "/api/me/memory-operations/" + op.id)
    ).json();
    if (current.status === "completed") return current;
    await page.waitForTimeout(100);
  }
  throw new Error("Synthetic memory operation did not complete");
}
module.exports.seedMemory = seedMemory;

// Radix restores focus after its close/unmount lifecycle, after hidden is observable.
async function waitForFocus(page, locator) {
  const element = await locator.elementHandle();
  if (!element) throw new Error("Focus return target is missing");
  try {
    await page.waitForFunction(
      (node) => node === document.activeElement,
      element,
      { timeout: 5000 },
    );
  } finally {
    await element.dispose();
  }
}
module.exports.waitForFocus = waitForFocus;
