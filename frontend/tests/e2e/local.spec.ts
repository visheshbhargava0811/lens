import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

/** Local tab (F-15): state from browser location, resolved on the device, with a manual picker. */
test.describe("local with location allowed", () => {
  test.use({ permissions: ["geolocation"], geolocation: { latitude: 28.61, longitude: 77.21 } }); // Delhi

  test("finds the state and lists its stories", async ({ page }) => {
    await page.goto("/local");
    await expect(page.getByRole("heading", { level: 2, name: "Delhi" })).toBeVisible();
    await expect(page.locator('[data-testid^="story-card-"]').first()).toBeVisible();
    await expect(page.getByLabel("State")).toHaveValue("delhi");
    expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([]);

    await page.reload(); // remembered in this browser
    await expect(page.getByLabel("State")).toHaveValue("delhi");
  });
});

test("location denied: explains and the picker still works", async ({ page }) => {
  await page.goto("/local"); // no geolocation permission granted
  await expect(page.getByRole("status")).toContainText("Choose your state");
  await page.getByLabel("State").selectOption("maharashtra");
  await expect(page.getByRole("heading", { level: 2, name: "Maharashtra" })).toBeVisible();
  await expect(page.getByTestId("empty-state")).toBeVisible();
});

test("only the state reaches the API, never coordinates", async ({ browser }) => {
  const context = await browser.newContext({
    permissions: ["geolocation"],
    geolocation: { latitude: 28.61, longitude: 77.21 },
  });
  const page = await context.newPage();
  const urls: string[] = [];
  page.on("request", (r) => urls.push(r.url()));
  const feed = page.waitForRequest((r) => r.url().includes("state=delhi"));
  await page.goto("/local");
  await feed;
  await expect(page.locator('[data-testid^="story-card-"]').first()).toBeVisible();
  expect(urls.filter((u) => /28\.61|77\.21/.test(u))).toEqual([]);
  await context.close();
});
