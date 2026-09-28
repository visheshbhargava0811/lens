import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

for (const locale of ["en", "hi"] as const) {
  test.describe(`shell (${locale})`, () => {
    test.beforeEach(async ({ context }) => {
      await context.addCookies([{ name: "NEXT_LOCALE", value: locale, url: "http://localhost:3100" }]);
    });

    test("renders with tokens and fonts", async ({ page }, info) => {
      await page.goto("/");
      await expect(page.locator("html")).toHaveAttribute("lang", locale);
      await expect(page.getByRole("heading", { level: 1 })).toHaveText(
        locale === "hi" ? "प्रमुख ख़बरें" : "Top stories",
      );

      const body = page.locator("body");
      await expect(body).toHaveCSS("background-color", "rgb(236, 237, 230)");
      await expect(body).toHaveCSS("color", "rgb(29, 30, 27)");
      const family = await body.evaluate((el) => getComputedStyle(el).fontFamily);
      expect(family).toMatch(/Noto Sans/);
      expect(family).toMatch(/Noto Sans Devanagari/);

      // Web fonts load lazily per unicode-range; load() waits and returns the faces that matched.
      const faces = await page.evaluate(async () => {
        const loaded = await document.fonts.load('16px "Noto Sans Devanagari"', "हिं");
        return loaded.map((f) => f.family);
      });
      expect(faces).toContain("Noto Sans Devanagari");

      const noOverflow = await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth);
      expect(noOverflow).toBe(true);

      await page.screenshot({ path: `test-results/shell-${locale}-${info.project.name}.png`, fullPage: true });
    });

    test("has no detectable a11y violations", async ({ page }) => {
      await page.goto("/");
      // The route streams; scan the rendered feed, not the loading skeleton.
      await expect(page.getByTestId("story-card-hero")).toBeVisible();
      const results = await new AxeBuilder({ page }).analyze();
      expect(results.violations).toEqual([]);
    });
  });
}

test("language switcher toggles UI language", async ({ page }) => {
  await page.goto("/");
  // A click that lands before hydration does nothing, so retry until the language changes.
  await expect(async () => {
    await page.getByRole("button", { name: "हिं" }).click();
    await expect(page.locator("html")).toHaveAttribute("lang", "hi", { timeout: 2_000 });
  }).toPass();
  await expect(async () => {
    await page.getByRole("button", { name: "EN" }).click();
    await expect(page.locator("html")).toHaveAttribute("lang", "en", { timeout: 2_000 });
  }).toPass();
});
