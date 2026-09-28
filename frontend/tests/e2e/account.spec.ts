import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

/** Google sign-in (ADR-0044): the sign-in page, then the header account menu once signed in. */
test("sign-in page states what Lens gets and links to the API flow", async ({ page }) => {
  await page.goto("/sign-in?next=/for-you");
  await expect(page.getByRole("heading", { level: 1, name: "Sign in to Lens" })).toBeVisible();
  await expect(page.getByText(/Not your email, name, photo or contacts/)).toBeVisible();
  const google = page.getByRole("link", { name: "Continue with Google" });
  await expect(google).toHaveAttribute("href", /\/auth\/google\/start\?next=%2Ffor-you$/);
  expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([]);
});

test("sign-in page never forwards to another site and explains errors", async ({ page }) => {
  await page.goto("/sign-in?next=//evil.example&error=cancelled");
  await expect(page.getByRole("alert").filter({ hasText: "Sign-in was cancelled" })).toHaveText(
    "Sign-in was cancelled. You can try again.",
  ); // Next's route announcer is also an alert
  await expect(page.getByRole("link", { name: "Continue with Google" })).toHaveAttribute(
    "href",
    /next=%2Fme$/,
  );
});

test("For you asks to sign in when signed out", async ({ page }) => {
  await page.goto("/for-you");
  await expect(page.getByText(/Sign in for personalization/)).toBeVisible();
  await expect(page.getByRole("main").getByRole("link", { name: "Sign in" })).toHaveAttribute(
    "href",
    "/sign-in?next=/for-you",
  );
  await expect(page.locator('[data-testid^="story-card-"]')).toHaveCount(0);
});

test.describe("signed in", () => {
  test.beforeEach(async ({ page }) => {
    await page.addInitScript(() => {
      (window as { __lensMockSignedIn?: boolean }).__lensMockSignedIn = true;
    });
  });

  test("account menu: quick preferences, links and sign out", async ({ page }) => {
    await page.goto("/");
    const trigger = page.getByRole("button", { name: "Account" });
    await trigger.click();
    const menu = page.getByTestId("account-menu");
    await expect(menu).toBeVisible();
    await expect(menu.getByText("Signed in with Google")).toBeVisible();

    await menu.getByLabel("Answer length").selectOption("short");
    await expect(menu.getByRole("status")).toHaveText("Saved");
    await menu.getByText("Sports", { exact: true }).click();
    await expect(menu.getByRole("checkbox", { name: "Sports" })).toBeChecked();
    await expect(menu.getByRole("link", { name: "All preferences and your data" })).toHaveAttribute("href", "/me");
    expect((await new AxeBuilder({ page }).include('[data-testid="account-menu"]').analyze()).violations).toEqual(
      [],
    );

    await menu.getByRole("button", { name: "Sign out" }).click();
    await expect(trigger).toBeHidden();
  });

  test("For you shows the feed once topics are followed", async ({ page }) => {
    await page.goto("/for-you");
    await expect(page.getByText("Follow some topics to see them here.")).toBeVisible();
  });

  test("sign-in page says you're already signed in", async ({ page }) => {
    await page.goto("/sign-in");
    await expect(page.getByText("You're signed in with Google.")).toBeVisible();
  });
});
