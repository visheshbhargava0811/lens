import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

/** Phase 9 acceptance (docs/12), signed in (ADR-0044): /me view, edit, delete-everything; no political field. */
test("me without sign-in asks to sign in", async ({ page }) => {
  await page.goto("/me");
  await expect(page.getByRole("heading", { name: "Sign in to set your preferences" })).toBeVisible();
  await expect(page.getByText(/any political preference/)).toBeVisible(); // stated as never stored
  await expect(page.getByRole("main").getByRole("link", { name: "Sign in" })).toHaveAttribute(
    "href",
    "/sign-in?next=/me",
  );
  await expect(page.getByLabel("Answer length")).toHaveCount(0);
});

test("me: edit preferences, delete everything", async ({ page }) => {
  await page.addInitScript(() => {
    (window as { __lensMockSignedIn?: boolean }).__lensMockSignedIn = true;
  });
  await page.goto("/me");
  await page.getByLabel("Answer length").selectOption("short");
  await expect(page.getByRole("status").filter({ hasText: "Saved" })).toHaveText("Saved");
  await page.getByRole("checkbox", { name: "Sports" }).check();
  const stored = page.getByTestId("stored-preferences");
  await expect(stored).toContainText("Answer length: Short");
  await expect(stored).toContainText("Topics you follow: Sports");
  const prefs = page.locator("section").filter({ has: page.getByRole("heading", { name: "Preferences" }) });
  await expect(prefs.getByText(/politic/i)).toHaveCount(1); // only the "Politics" topic chip: no leaning field

  const axe = await new AxeBuilder({ page }).analyze();
  expect(
    axe.violations.filter((v) => v.impact === "serious" || v.impact === "critical").map((v) => v.id),
  ).toEqual([]);

  await page.getByRole("button", { name: "Delete everything" }).click();
  await page.getByRole("button", { name: "Yes, delete everything" }).click();
  await expect(page.getByText("Everything was deleted, including your sign-in.")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Sign in to set your preferences" })).toBeVisible();
});
