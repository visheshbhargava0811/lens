import AxeBuilder from "@axe-core/playwright";
import { expect, type Page, test } from "@playwright/test";

const STORY = "/story/central-government-proposes-rules-for-ride-hailing-apps";
const STORY_HI = "/story/state-approves-budget-for-new-metro-line";
const LIMITED = "/story/researchers-report-results-from-coastal-flood-warning-pilot";

async function expectHealthyPage(page: Page, name: string, project: string) {
  // Routes stream behind loading.tsx skeletons; wait until the skeleton is gone.
  await expect(page.locator('[role="status"]')).toHaveCount(0);
  await expect(page.locator("h1").first()).toBeAttached();
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  expect(overflow, "no horizontal page scroll").toBeLessThanOrEqual(0);
  const axe = await new AxeBuilder({ page }).analyze();
  const serious = axe.violations.filter((v) => v.impact === "serious" || v.impact === "critical");
  expect(serious.map((v) => `${v.id}: ${v.nodes.map((n) => n.target).join(" ")}`)).toEqual([]);
  await page.screenshot({ path: `test-results/page-${name}-${project}.png`, fullPage: true });
}

const pages: [string, string][] = [
  ["home", "/"],
  ["story", STORY],
  ["story-hi", STORY_HI],
  ["story-limited", LIMITED],
  ["blindspot-stance", "/blindspot"],
  ["blindspot-language", "/blindspot?type=language"],
  ["methodology", "/methodology"],
  ["topic-empty", "/topic/entertainment"],
];

test.describe("pages render from fixtures", () => {
  for (const [name, path] of pages) {
    test(name, async ({ page }, info) => {
      const res = await page.goto(path);
      expect(res?.status()).toBe(200);
      await expectHealthyPage(page, name, info.project.name);
    });
  }
});

test("home shows hero, cards, blindspot rail and coverage figures with confidence", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByTestId("story-card-hero")).toHaveCount(1);
  // 7 on the first page; infinite scroll may already have appended page 2 on tall viewports.
  expect(await page.getByTestId("story-card-standard").count()).toBeGreaterThanOrEqual(7);
  await expect(page.getByTestId("flag-chip").first()).toBeVisible();
  // G-BIAS-01 in the UI: every bar sits next to a confidence label and a methodology link.
  for (const bar of await page.getByTestId("coverage-bar").all()) {
    const card = bar.locator("xpath=..");
    const hasMeta = (await card.getByText(/Confidence:/).count()) > 0;
    const inCompact = (await bar.locator("xpath=ancestor::article[@data-testid='story-card-compact']").count()) > 0;
    if (!inCompact) expect(hasMeta).toBe(true);
  }
});

test("load more appends the next page, then reports the end", async ({ page }) => {
  await page.goto("/");
  const next = page.getByRole("link", { name: "Neighbouring countries sign river-water data sharing pact" });
  await expect(next).toHaveCount(0);
  // On tall viewports infinite scroll may fire first; otherwise the visible button loads the page.
  if ((await next.count()) === 0) {
    await page.getByRole("button", { name: "Load more stories" }).click({ timeout: 5000 }).catch(() => {});
  }
  await expect(next).toBeVisible();
  await expect(page.getByText("You've reached the end of the feed.")).toBeVisible();
});

test("coverage bar tooltip appears on keyboard focus", async ({ page }) => {
  await page.goto(STORY);
  const bar = page.getByRole("img", { name: /^Coverage by 13 sources/ }).first();
  await bar.focus();
  await expect(bar.locator("xpath=following-sibling::div")).toBeVisible();
});

test("citation chip opens a popover and reveals its article row", async ({ page }) => {
  await page.goto(STORY);
  // Filter the list first so the cited row is hidden; the citation must clear filters.
  await page.getByRole("group", { name: "Filter by outlet bias" }).getByRole("button", { name: /^Right/ }).click();
  const chip = page.getByTestId("citation-chip").first();
  const articleId = await chip.getAttribute("data-article-id");
  await chip.click();
  const popover = page.getByTestId("citation-popover");
  await expect(popover).toBeVisible();
  await expect(popover).toContainText("Example Times");
  await popover.getByRole("button", { name: "Show in source list" }).click();
  const row = page.locator(`#article-${articleId}`);
  await expect(row).toBeVisible();
  await expect(row).toHaveAttribute("data-highlighted", "true");
  await expect(row).toBeFocused();
});

test("source filters narrow the list", async ({ page }) => {
  await page.goto(STORY);
  await expect(page.getByText("15 articles")).toBeVisible();
  const left = page.getByRole("group", { name: "Filter by outlet bias" }).getByRole("button", { name: /^Left/ });
  const leftCount = Number(await left.locator("span").innerText());
  expect(leftCount).toBeGreaterThan(0);
  await left.click();
  await expect(page.getByText(`${leftCount} article${leftCount === 1 ? "" : "s"}`, { exact: true })).toBeVisible();
  await expect(page.getByText("Bias: Left").first()).toBeVisible();
});

test("syndicated rows and unrated sources are labeled", async ({ page }) => {
  await page.goto(STORY);
  await expect(page.getByText("Also carried by 2 outlets")).toBeVisible();
  await expect(page.getByText("Syndicated copy").first()).toBeVisible();
  await expect(page.getByText("Factuality: Not rated").first()).toBeVisible();
  await expect(page.getByTestId("verified")).toBeVisible();
  await expect(page.getByTestId("limitations")).toContainText("Based on headlines and summaries");
});

test("Hindi headline renders with lang and Indic line height; legend shows outlet bias", async ({ page }) => {
  await page.goto(STORY_HI);
  const h1 = page.getByRole("heading", { level: 1 });
  await expect(h1).toHaveAttribute("lang", "hi");
  const ratio = await h1.evaluate((el) => parseFloat(getComputedStyle(el).lineHeight) / parseFloat(getComputedStyle(el).fontSize));
  expect(ratio).toBeCloseTo(1.35, 2);
  const legend = page.getByRole("list", { name: "Political lean of the outlets covering this story" }).filter({ visible: true }).first();
  for (const label of ["Left", "Center", "Right", "Not rated"]) await expect(legend.getByText(label, { exact: true })).toBeVisible();
});

test("limited coverage replaces the bar and still lists sources", async ({ page }) => {
  await page.goto(LIMITED);
  await expect(page.getByTestId("coverage-limited").first()).toContainText("Limited coverage: only 2 sources so far");
  await expect(page.getByTestId("article-row")).toHaveCount(2);
  await expect(page.getByText("A summary isn't ready yet.")).toBeVisible();
});

test("empty topic shows an empty state", async ({ page }) => {
  await page.goto("/topic/entertainment");
  await expect(page.getByTestId("empty-state")).toContainText("No Entertainment stories yet");
});

test("feed and story errors show a plain message and a retry button", async ({ page }) => {
  await page.goto("/topic/fixture-error");
  await expect(page.getByTestId("error-state")).toContainText("Couldn't load stories. Check your connection and try again.");
  await expect(page.getByRole("button", { name: "Try again" })).toBeVisible();

  await page.goto("/story/fixture-error");
  await expect(page.getByTestId("error-state")).toContainText("Couldn't load this story.");
});

test("unknown story shows not found", async ({ page }) => {
  // Status is 200 because the route streams (loading.tsx); Next marks the page noindex instead.
  await page.goto("/story/does-not-exist");
  await expect(page.getByText("This story doesn't exist or was removed.")).toBeVisible();
});

test("Hindi UI localizes coverage copy but keeps source headlines in their script", async ({ page, context }) => {
  await context.addCookies([{ name: "NEXT_LOCALE", value: "hi", url: "http://localhost:3100" }]);
  await page.goto(STORY);
  await expect(page.getByRole("heading", { name: "सारांश" })).toBeVisible();
  await expect(page.getByText("Draft rules cap surge pricing for ride-hailing apps")).toHaveAttribute("lang", "en");
  await expectHealthyPage(page, "story-hi-ui", "hi");
});

test("keyboard: skip link, then tab into the story list", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByTestId("story-card-hero")).toBeVisible();
  await page.keyboard.press("Tab");
  await expect(page.getByRole("link", { name: "Skip to content" })).toBeFocused();
  await page.keyboard.press("Enter");
  await page.keyboard.press("Tab");
  const focused = await page.evaluate(() => document.activeElement?.closest("main") !== null);
  expect(focused).toBe(true);
});
