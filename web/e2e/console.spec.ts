import { expect, type Page, test } from "@playwright/test";

/** Fails the test on any script error; 4xx answers the console handles on purpose are not errors. */
function watchErrors(page: Page): string[] {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(String(e)));
  page.on("console", (m) => {
    if (m.type() === "error" && !m.text().includes("status of 4")) errors.push(m.text());
  });
  return errors;
}

async function noSideways(page: Page) {
  const wide = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  expect(wide).toBeLessThanOrEqual(1);
}

test("every view loads from the server without errors or sideways scrolling", async ({ page }) => {
  const errors = watchErrors(page);
  await page.goto("/");
  await expect(page.getByRole("heading", { level: 1, name: "The line" })).toBeVisible();
  await expect(page.getByRole("region", { name: /^FX-A/ })).toBeVisible();
  await noSideways(page);
  for (const [link, heading] of [
    ["Issues", "Issues"],
    ["Airframes", "Airframes"],
    ["Releases", "Releases"],
    ["Work instruction", "Work instruction"],
  ] as const) {
    await page
      .getByRole("navigation", { name: "Main" })
      .getByRole("link", { name: link, exact: true })
      .click();
    await expect(page.getByRole("heading", { level: 1, name: heading })).toBeVisible();
    await expect(page.getByRole("status", { name: /^Loading/ })).toHaveCount(0);
    await noSideways(page);
  }
  expect(errors).toEqual([]);
});

test("from a systemic slot to an airframe's paper trail and certificate", async ({ page }) => {
  const errors = watchErrors(page);
  await page.goto("/");
  const flagged = page
    .getByRole("link", { name: /^Slot FX-.*: units$/ })
    .filter({ hasText: "Systemic" })
    .first();
  await flagged.click();
  await expect(page.getByText(/^Every airframe that went through slot FX-/)).toBeVisible();
  await page.getByRole("group", { name: "Status" }).getByText("Released", { exact: true }).click();
  await expect(page).toHaveURL(/status=released/);
  const table = page.getByRole("region", { name: "Airframes" });
  await expect(table.getByText("Held", { exact: true })).toHaveCount(0); // the released list, not the one before
  await table.getByRole("link").first().click();
  await expect(page.getByText(/^Trail verified: \d+ events/)).toBeVisible();
  const download = page.waitForEvent("download");
  await page.getByRole("button", { name: "Download certificate" }).click();
  expect((await download).suggestedFilename()).toMatch(/-software-certificate\.json$/);
  await noSideways(page);
  expect(errors).toEqual([]);
});

test("the lead marks a systemic issue fixed and the note stays with it", async ({ page }) => {
  const errors = watchErrors(page);
  await page.goto("/issues");
  await page.getByLabel("Acting as").selectOption("lead");
  await page.getByLabel("Your name").fill("E2E Lead");
  await page.waitForTimeout(500); // the name is sent once typing pauses
  const systemic = page.getByRole("region", { name: /^Systemic/ });
  const card = systemic.getByRole("article").first();
  await card.getByRole("button", { name: "Act on this" }).click();
  const dialog = page.getByRole("dialog");
  await dialog.getByText("Mark fixed", { exact: true }).click();
  const note = `fixture inspected ${Date.now()}`;
  await dialog.getByLabel("Note", { exact: true }).fill(note);
  await dialog.getByRole("button", { name: "Mark fixed" }).click();
  await expect(dialog.getByText("Marked fixed by E2E Lead.")).toBeVisible();
  await dialog.getByRole("button", { name: "Close" }).click();
  await page.reload();
  await expect(page.getByText(note)).toBeVisible();
  expect(errors).toEqual([]);
});

test("an operator sees the issues but cannot act on them", async ({ page }) => {
  await page.goto("/issues");
  await page.getByLabel("Acting as").selectOption("operator");
  await page
    .getByRole("region", { name: /^Systemic/ })
    .getByRole("button", { name: "Act on this" })
    .first()
    .click();
  await expect(page.getByRole("dialog").getByText(/Operators see the issues/)).toBeVisible();
});

test("the recall list follows the chosen version", async ({ page }) => {
  const errors = watchErrors(page);
  await page.goto("/releases");
  await expect(page.getByText(/released airframes carry Flight controller/)).toBeVisible();
  await page.getByRole("radio", { name: "Mission computer" }).check({ force: true });
  await expect(page.getByText(/released airframes carry Mission computer/)).toBeVisible();
  await noSideways(page);
  expect(errors).toEqual([]);
});
