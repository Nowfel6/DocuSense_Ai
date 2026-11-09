import { expect, test } from "@playwright/test";

test("foundation preview exposes the shell and primary controls", async ({ page }, testInfo) => {
  await page.goto("/foundation-preview");
  await expect(page.getByRole("heading", { name: "Frontend foundation" })).toBeVisible();
  if (testInfo.project.name === "narrow-390") {
    await expect(page.getByRole("button", { name: "Open navigation" })).toBeVisible();
  } else if (testInfo.project.name === "medium-768") {
    await expect(page.getByRole("navigation", { name: "Primary navigation" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Open navigation" })).toBeVisible();
    await expect(page.locator(".ds-sidebar")).toHaveCSS("width", "72px");
  } else {
    await expect(page.getByRole("navigation", { name: "Primary navigation" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Open navigation" })).toBeHidden();
    await expect(page.getByRole("button", { name: "Collapse navigation" })).toBeVisible();
    await expect(page.locator(".ds-sidebar")).toHaveCSS("width", "248px");
  }
  await expect(page.getByText("DESIGN_FIXTURE", { exact: false })).toBeVisible();
  await expect(page.getByRole("button", { name: "Primary action" })).toBeVisible();
});

test("skip link and dialog remain keyboard operable", async ({ page }) => {
  await page.goto("/foundation-preview");
  const skipLink = page.getByRole("link", { name: "Skip to main content" });
  await skipLink.focus();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("main")).toBeFocused();
  await page.getByRole("button", { name: "Open dialog" }).click();
  await expect(page.getByRole("dialog")).toBeVisible();
  await page.getByRole("button", { name: "Close dialog" }).click();
  await expect(page.getByRole("button", { name: "Open dialog" })).toBeFocused();
});

test("mobile navigation opens as a labeled drawer", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "narrow-390", "Narrow-screen shell behavior");
  await page.goto("/foundation-preview");
  await page.getByRole("button", { name: "Open navigation" }).click();
  await expect(page.getByRole("dialog", { name: "Navigation" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Upload" })).toBeVisible();
});

test("motion and texture honor system accessibility preferences", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce", forcedColors: "active" });
  await page.goto("/foundation-preview");
  const animationDuration = await page.locator(".ds-skeleton").first().evaluate((element) =>
    Number.parseFloat(getComputedStyle(element).animationDuration),
  );
  const textureDisplay = await page.locator("body").evaluate((element) =>
    getComputedStyle(element, "::before").display,
  );
  expect(animationDuration).toBeLessThanOrEqual(0.001);
  expect(textureDisplay).toBe("none");
});
