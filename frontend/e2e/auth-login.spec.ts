import { expect, test } from "@playwright/test";

test.beforeEach(async ({ context }) => {
  await context.clearCookies();
});

test("renders the approved login hierarchy and safe query states", async ({ page }) => {
  await page.goto("/login?unknown=%3Cscript%3Ealert(1)%3C%2Fscript%3E");
  await expect(page.locator(".ds-login-form")).toHaveAttribute("data-hydrated", "true");
  await expect(page.getByRole("heading", { name: "Sign in to DocuSense" })).toBeVisible();
  await expect(page.getByText("Use your organization account to continue.")).toBeVisible();
  await expect(page.getByLabel("Email")).toHaveAttribute("autocomplete", "email");
  await expect(page.getByLabel("Password", { exact: true })).toHaveAttribute("autocomplete", "current-password");
  await expect(page.getByText("<script>")).toHaveCount(0);
  await expect(page.locator(".ds-login-card")).toHaveCSS("max-width", "none");
  expect((await page.locator(".ds-login-card").boundingBox())?.width).toBeLessThanOrEqual(440);

  await page.goto("/login?signedOut=1");
  await expect(page.getByText("You’re signed out")).toBeVisible();
  await page.goto("/login?signedOut=1&reason=session-expired");
  await expect(page.getByText("Your session ended")).toBeVisible();
  await expect(page.getByText("You’re signed out")).toHaveCount(0);
});

test("validates fields and toggles password without losing its value", async ({ page }) => {
  await page.goto("/login");
  await expect(page.locator(".ds-login-form")).toHaveAttribute("data-hydrated", "true");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByLabel("Email")).toBeFocused();
  await expect(page.getByText("Enter a valid email address.")).toBeVisible();
  await expect(page.getByText("Enter your password.")).toBeVisible();

  await page.getByLabel("Password", { exact: true }).fill("preserved secret");
  await page.getByRole("button", { name: "Show password" }).click();
  await expect(page.getByLabel("Password", { exact: true })).toHaveAttribute("type", "text");
  await expect(page.getByLabel("Password", { exact: true })).toHaveValue("preserved secret");
});

test("maps invalid credentials without disclosing backend details", async ({ page }) => {
  await page.goto("/login");
  await expect(page.locator(".ds-login-form")).toHaveAttribute("data-hydrated", "true");
  await page.getByLabel("Email").fill("operator@example.test");
  await page.getByLabel("Password", { exact: true }).fill("wrong password");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByText("Sign in failed")).toBeVisible();
  await expect(page.getByText("The email or password is incorrect.")).toBeVisible();
  await expect(page.getByLabel("Password", { exact: true })).toBeFocused();
  await expect(page.getByLabel("Password", { exact: true })).toHaveValue("");
  await expect(page.getByText("Authentication request was rejected.")).toHaveCount(0);
});

test("creates a server session, protects dashboard, and signs out", async ({ page }) => {
  await page.goto("/dashboard");
  await expect(page).toHaveURL(/\/login$/);
  await expect(page.locator(".ds-login-form")).toHaveAttribute("data-hydrated", "true");

  await page.getByLabel("Email").fill("operator@example.test");
  await page.getByLabel("Password", { exact: true }).fill("correct password");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/dashboard$/);
  await expect(page.getByRole("heading", { name: "Workspace ready" })).toBeVisible();
  await expect(page.getByText("No document or analytics data is shown on this temporary screen.")).toBeVisible();
  await expect(page.getByRole("link", { name: "All documents" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Notifications" })).toHaveCount(0);

  await page.reload();
  await expect(page.getByRole("heading", { name: "Workspace ready" })).toBeVisible();
  await page.goto("/login");
  await expect(page).toHaveURL(/\/dashboard$/);
  await expect(page.locator(".ds-app-shell[data-hydrated]")).toHaveAttribute("data-hydrated", "true");

  await page.getByLabel("Account menu for Example Operator").click();
  await page.getByRole("button", { name: "Sign out" }).click();
  await expect(page).toHaveURL(/\/login\?signedOut=1$/);
  await expect(page.getByText("You’re signed out")).toBeVisible();

  await page.goto("/dashboard");
  await expect(page).toHaveURL(/\/login$/);
});
