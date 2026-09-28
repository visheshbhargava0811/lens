import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

/** Phase 9 acceptance (docs/12): /me view, edit, delete-everything; consent gate; no political field. */
test("me: consent gate, edit preferences, delete everything", async ({
  page,
}) => {
  await page.goto("/me");
  await expect(
    page.getByRole("heading", { name: "Turn on personalization?" }),
  ).toBeVisible();
  await expect(page.getByText(/any political preference/)).toBeVisible(); // stated as never stored
  await page.getByRole("button", { name: "Turn on personalization" }).click();

  await page.getByLabel("Answer length").selectOption("short");
  await expect(page.getByRole("status")).toHaveText("Saved");
  await page.getByRole("checkbox", { name: "Sports" }).check();
  const stored = page.getByTestId("stored-preferences");
  await expect(stored).toContainText("Answer length: Short");
  await expect(stored).toContainText("Topics you follow: Sports");
  const prefs = page
    .locator("section")
    .filter({ has: page.getByRole("heading", { name: "Preferences" }) });
  await expect(prefs.getByText(/politic/i)).toHaveCount(1); // only the "Politics" topic: no leaning field exists // only the "Politics" topic chip: no leaning field

  const axe = await new AxeBuilder({ page }).analyze();
  expect(
    axe.violations
      .filter((v) => v.impact === "serious" || v.impact === "critical")
      .map((v) => v.id),
  ).toEqual([]);

  await page.getByRole("button", { name: "Delete everything" }).click();
  await page.getByRole("button", { name: "Yes, delete everything" }).click();
  await expect(
    page.getByText("Everything was deleted. Personalization is off."),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Turn on personalization" }),
  ).toBeVisible();
});

test("sign-in leads to the consent page", async ({ page }) => {
  await page.goto("/sign-in");
  await expect(page).toHaveURL(/\/me$/);
});
