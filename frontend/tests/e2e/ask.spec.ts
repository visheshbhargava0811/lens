import AxeBuilder from "@axe-core/playwright";
import { expect, type Page, test } from "@playwright/test";

async function ask(page: Page, q: string) {
  await page.goto("/ask");
  await page.getByTestId("ask-input").fill(q);
  await page.getByTestId("ask-submit").click();
}

async function expectAccessible(page: Page, name: string, project: string) {
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  expect(overflow, "no horizontal page scroll").toBeLessThanOrEqual(0);
  const axe = await new AxeBuilder({ page }).analyze();
  const serious = axe.violations.filter((v) => v.impact === "serious" || v.impact === "critical");
  expect(serious.map((v) => `${v.id}: ${v.nodes.map((n) => n.target).join(" ")}`)).toEqual([]);
  await page.screenshot({ path: `test-results/ask-${name}-${project}.png`, fullPage: true });
}

test("answer: cited, verified, coverage from data with methodology, sources with bias", async ({ page }, info) => {
  await ask(page, "what happened with the ride-hailing rules");
  const card = page.getByTestId("answer-card");
  await expect(card).toBeVisible();
  await expect(page.getByTestId("ask-status")).toHaveText("");
  await expect(card.getByTestId("verified")).toBeVisible();
  expect(await card.getByTestId("citation-chip").count()).toBeGreaterThan(0);
  await expect(card.getByRole("link", { name: /how this is calculated/i }).first()).toBeAttached();
  await expect(card.getByTestId("limitations")).toContainText("headlines and short feed summaries");
  await card.getByTestId("citation-chip").first().click();
  await expect(page.getByTestId("citation-popover")).toBeVisible();
  await page.keyboard.press("Escape");
  await expectAccessible(page, "answer", info.project.name);
});

test("loaded question shows the neutral query, editable, and the premise limitation", async ({ page }) => {
  await ask(page, "why is the government rigging the numbers");
  await expect(page.getByTestId("neutral-note")).toBeVisible();
  await expect(page.locator("#neutral-input")).toHaveValue("What has been reported about the numbers?");
  await expect(page.getByTestId("limitations")).toContainText("None of the retrieved articles report that");
});

test("abstain shows the plain explanation and closest stories, no answer", async ({ page }, info) => {
  await ask(page, "who won the cricket final");
  const box = page.getByTestId("abstain-state");
  await expect(box).toContainText("There isn't enough reliable coverage");
  expect(await box.getByTestId("story-card-standard").count()).toBe(2);
  await expect(page.getByTestId("answer-card")).toHaveCount(0);
  await expectAccessible(page, "abstain", info.project.name);
});

test("out of scope and sensitive topics say so", async ({ page }) => {
  await ask(page, "write a slogan for a party");
  await expect(page.getByTestId("abstain-state")).toContainText("Lens covers news reporting");
  await ask(page, "communal riot today");
  await expect(page.getByTestId("abstain-state")).toContainText("only show reviewed summaries");
});

test("rate limit tells the reader when to try again", async ({ page }) => {
  await ask(page, "too fast");
  await expect(page.getByTestId("error-state")).toContainText("Try again in 12 seconds");
});

test("a ?q= link asks immediately", async ({ page }) => {
  await page.goto("/ask?q=what%20happened");
  await expect(page.getByTestId("answer-card")).toBeVisible();
});
