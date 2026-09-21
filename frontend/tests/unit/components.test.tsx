import { screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { CoverageBar } from "@/components/coverage/CoverageBar";
import { StanceLegend } from "@/components/coverage/StanceLegend";
import { ArticleRow } from "@/components/story/ArticleRow";
import { StoryCard } from "@/components/story/StoryCard";
import type { ArticleRow as Row } from "@/lib/api/types";
import { buildCoverage, dominantTarget } from "@/lib/coverage";
import { stories } from "@/mocks/fixtures";

import { renderWithIntl } from "./render";

describe("CoverageBar", () => {
  it("has a full screen-reader alternative matching docs/10", () => {
    const coverage = buildCoverage({ critical: 18, balanced: 12, supportive: 9 }, 3, "medium");
    renderWithIntl(<CoverageBar coverage={coverage} sourceCount={42} />);
    expect(screen.getByRole("img")).toHaveAccessibleName(
      "Coverage by 42 sources: 43 percent critical of the government, 29 percent balanced, " +
        "21 percent supportive of the government, 7 percent unclassified. Confidence medium.",
    );
  });

  it("always shows confidence and a methodology link", () => {
    const coverage = buildCoverage({ critical: 2, balanced: 2, supportive: 2 }, 0, "low");
    renderWithIntl(<CoverageBar coverage={coverage} sourceCount={6} />);
    expect(screen.getByText("Confidence: low")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "How this is calculated" })).toHaveAttribute("href", "/methodology#stance");
  });

  it("renders segment widths from source counts and hides empty buckets", () => {
    const coverage = buildCoverage({ critical: 1, balanced: 0, supportive: 3 }, 0, "low");
    const { container } = renderWithIntl(<CoverageBar coverage={coverage} sourceCount={4} />);
    const segs = [...container.querySelectorAll("[data-segment]")] as HTMLElement[];
    expect(segs.map((s) => [s.dataset.segment, s.style.width])).toEqual([
      ["critical", "25%"],
      ["supportive", "75%"],
    ]);
  });

  it("renders the limited state below min_sources, with no bar", () => {
    const coverage = buildCoverage({ critical: 1, balanced: 1, supportive: 0 }, 0, "low");
    renderWithIntl(<CoverageBar coverage={coverage} sourceCount={2} />);
    expect(screen.queryByRole("img")).toBeNull();
    expect(
      screen.getByText("Limited coverage: only 2 sources so far. A coverage split needs at least 4."),
    ).toBeInTheDocument();
  });
});

describe("StanceLegend", () => {
  it("names the target when it is not the central government", () => {
    const coverage = buildCoverage({ critical: 2, balanced: 1, supportive: 1 }, 0, "low");
    renderWithIntl(<StanceLegend coverage={coverage} target="state_govt" />);
    expect(screen.getByText("Critical of the state government")).toBeInTheDocument();
    expect(screen.getByText("Unclassified")).toBeInTheDocument();
  });

  it("dominantTarget picks the most common non-none target", () => {
    const a = (target: Row["stance"]["target"]) => ({ stance: { target } });
    expect(dominantTarget([a("state_govt"), a("state_govt"), a("central_govt"), a("none")])).toBe("state_govt");
    expect(dominantTarget([a("none")])).toBe("central_govt");
  });
});

const baseRow: Row = {
  id: "a1",
  source: { id: "s1", name: "Example Outlet", logo_url: null, language: "hi" },
  headline: "हेडलाइन मूल भाषा में",
  headline_lang: "hi",
  published_at: "2026-09-21T10:00:00Z",
  url: "https://example.org/a1",
  stance: { value: "critical", target: "central_govt", confidence: "medium" },
  analysis_depth: "snippet",
  source_factuality: null,
  source_ownership: null,
  is_syndicated: false,
  also_carried_by: [],
};

describe("ArticleRow", () => {
  it("shows Not rated, unknown owner, depth note, and keeps the headline's language", () => {
    renderWithIntl(<ArticleRow article={baseRow} />);
    expect(screen.getByText("Factuality: Not rated")).toBeInTheDocument();
    expect(screen.getByText("Owner: Unknown")).toBeInTheDocument();
    expect(screen.getByText("Based on headline and summary.")).toBeInTheDocument();
    expect(screen.getByText("हेडलाइन मूल भाषा में")).toHaveAttribute("lang", "hi");
  });

  it("opens the source in a new tab safely", () => {
    renderWithIntl(<ArticleRow article={baseRow} />);
    const link = screen.getByRole("link", { name: /Read at Example Outlet/ });
    expect(link).toHaveAttribute("target", "_blank");
    expect(link).toHaveAttribute("rel", "noopener noreferrer");
  });

  it("labels syndication and low-confidence stance", () => {
    renderWithIntl(
      <ArticleRow
        article={{
          ...baseRow,
          analysis_depth: "full_text",
          also_carried_by: ["A", "B"],
          stance: { value: "critical", target: "state_govt", confidence: "low" },
        }}
      />,
    );
    expect(screen.getByText("Also carried by 2 outlets")).toBeInTheDocument();
    expect(screen.getByText("Unclassified, confidence low")).toBeInTheDocument();
    expect(screen.queryByText("Based on headline and summary.")).toBeNull();
  });
});

describe("StoryCard", () => {
  it.each(["hero", "standard", "compact"] as const)("%s variant is one link with the headline", (variant) => {
    renderWithIntl(<StoryCard story={stories[0]} variant={variant} />);
    const card = screen.getByTestId(`story-card-${variant}`);
    const link = within(card).getByRole("link", { name: stories[0].headline });
    expect(link).toHaveAttribute("href", `/story/${stories[0].slug}`);
  });

  it("shows a flag chip for blindspot stories", () => {
    const story = stories.find((s) => s.blindspot?.type === "language")!;
    renderWithIntl(<StoryCard story={story} />);
    expect(screen.getByTestId("flag-chip")).toHaveTextContent("Covered mostly in Hindi, little in English");
  });
});
