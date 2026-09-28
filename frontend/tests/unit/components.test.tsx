import { screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { AnswerCard } from "@/components/ask/AnswerCard";
import { CoverageBar } from "@/components/coverage/CoverageBar";
import { BiasLegend } from "@/components/coverage/BiasLegend";
import { ArticleRow } from "@/components/story/ArticleRow";
import { StoryCard } from "@/components/story/StoryCard";
import type { AskAnswer, ArticleRow as Row } from "@/lib/api/types";
import { buildCoverage } from "@/lib/coverage";
import { stories } from "@/mocks/fixtures";

import { renderWithIntl } from "./render";

describe("CoverageBar", () => {
  it("has a full screen-reader alternative matching docs/10", () => {
    const coverage = buildCoverage(
      { left: 18, center: 12, right: 9 },
      3,
      "medium",
    );
    renderWithIntl(<CoverageBar coverage={coverage} sourceCount={42} />);
    expect(screen.getByRole("img")).toHaveAccessibleName(
      "Coverage by 42 sources: 43 percent rated Left, 29 percent rated Center, " +
        "21 percent rated Right, 7 percent not rated. Confidence medium.",
    );
  });

  it("always shows confidence and a methodology link", () => {
    const coverage = buildCoverage({ left: 2, center: 2, right: 2 }, 0, "low");
    renderWithIntl(<CoverageBar coverage={coverage} sourceCount={6} />);
    expect(screen.getByText("Confidence: low")).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: "How this is calculated" }),
    ).toHaveAttribute("href", "/methodology#bias");
  });

  it("renders segment widths from source counts and hides empty buckets", () => {
    const coverage = buildCoverage({ left: 1, center: 0, right: 3 }, 0, "low");
    const { container } = renderWithIntl(
      <CoverageBar coverage={coverage} sourceCount={4} />,
    );
    const segs = [
      ...container.querySelectorAll("[data-segment]"),
    ] as HTMLElement[];
    expect(segs.map((s) => [s.dataset.segment, s.style.width])).toEqual([
      ["left", "25%"],
      ["right", "75%"],
    ]);
  });

  it("renders the limited state below min_sources, with no bar", () => {
    const coverage = buildCoverage({ left: 1, center: 1, right: 0 }, 0, "low");
    renderWithIntl(<CoverageBar coverage={coverage} sourceCount={2} />);
    expect(screen.queryByRole("img")).toBeNull();
    expect(
      screen.getByText(
        "Limited coverage: only 2 sources so far. A coverage split needs at least 4.",
      ),
    ).toBeInTheDocument();
  });
});

describe("BiasLegend", () => {
  it("labels Left, Center, Right and Not rated with counts", () => {
    const coverage = buildCoverage(
      { left: 2, center: 1, right: 1 },
      1,
      "medium",
    );
    renderWithIntl(<BiasLegend coverage={coverage} />);
    for (const label of ["Left", "Center", "Right", "Not rated"])
      expect(screen.getByText(label)).toBeInTheDocument();
  });
});

const baseRow: Row = {
  id: "a1",
  source: { id: "s1", name: "Example Outlet", logo_url: null, language: "hi" },
  headline: "हेडलाइन मूल भाषा में",
  headline_lang: "hi",
  published_at: "2026-09-21T10:00:00Z",
  url: "https://example.org/a1",
  analysis_depth: "snippet",
  bias: "unrated",
  source_bias: null,
  source_factuality: null,
  source_ownership: null,
  is_syndicated: false,
  also_carried_by: [],
};

describe("ArticleRow", () => {
  it("shows Not rated, unknown owner, depth note, and keeps the headline's language", () => {
    renderWithIntl(<ArticleRow article={baseRow} />);
    expect(screen.getByText("Factuality: Not rated")).toBeInTheDocument();
    expect(screen.getByText("Bias: Not rated")).toBeInTheDocument();
    expect(screen.getByText("Owner: Unknown")).toBeInTheDocument();
    expect(
      screen.getByText("Based on headline and summary."),
    ).toBeInTheDocument();
    expect(screen.getByText("हेडलाइन मूल भाषा में")).toHaveAttribute(
      "lang",
      "hi",
    );
  });

  it("opens the source in a new tab safely", () => {
    renderWithIntl(<ArticleRow article={baseRow} />);
    const link = screen.getByRole("link", { name: /Read at Example Outlet/ });
    expect(link).toHaveAttribute("target", "_blank");
    expect(link).toHaveAttribute("rel", "noopener noreferrer");
  });

  it("labels syndication and shows the rater's own bias wording, linked to their method", () => {
    renderWithIntl(
      <ArticleRow
        article={{
          ...baseRow,
          analysis_depth: "full_text",
          also_carried_by: ["A", "B"],
          bias: "left",
          source_bias: {
            rater: "Example Rater",
            value: "Left-Center",
            method_url: "https://example.org/m",
            confidence: "medium",
          },
        }}
      />,
    );
    expect(screen.getByText("Also carried by 2 outlets")).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: /Bias: Left-Center/ }),
    ).toHaveAttribute("href", "https://example.org/m");
    expect(screen.queryByText("Based on headline and summary.")).toBeNull();
  });
});

describe("StoryCard", () => {
  it.each(["hero", "standard", "compact"] as const)(
    "%s variant is one link with the headline",
    (variant) => {
      renderWithIntl(<StoryCard story={stories[0]} variant={variant} />);
      const card = screen.getByTestId(`story-card-${variant}`);
      const link = within(card).getByRole("link", {
        name: stories[0].headline,
      });
      expect(link).toHaveAttribute("href", `/story/${stories[0].slug}`);
    },
  );

  it("shows a flag chip for blindspot stories", () => {
    const story = stories.find((s) => s.blindspot?.type === "language")!;
    renderWithIntl(<StoryCard story={story} />);
    expect(screen.getByTestId("flag-chip")).toHaveTextContent(
      "Covered mostly in Hindi, little in English",
    );
  });
});

describe("AnswerCard (Phase 8)", () => {
  const base = {
    basis: "live" as const,
    lang: "en",
    tldr: [{ text: "Phase 1 began.", citations: [] }],
    what_happened: [],
    agreements: [],
    disagreements: [],
    premises_addressed: [],
    limitations: [],
    follow_up_questions: [],
    coverage: buildCoverage({ left: 2, center: 1, right: 1 }, 0, "low"),
    story_ids: [],
    articles: [],
    verified: true as const,
    fact_checks: [
      {
        claim: "A viral video shows the bridge collapse.",
        fact_checker: "BOOM",
        rating: "False",
        rating_normalized: "false" as const,
        match: "same_claim" as const,
        url: "https://boom.example/1",
        published_at: null,
      },
      {
        claim: "An old photo shows the rescue.",
        fact_checker: "Vishvas News",
        rating: "Misleading",
        rating_normalized: "misleading" as const,
        match: "related" as const,
        url: "https://vishvas.example/2",
        published_at: null,
      },
    ],
  } as unknown as AskAnswer;

  it("labels translated answers and not English ones", () => {
    const { unmount } = renderWithIntl(
      <AnswerCard
        answer={{ ...base, lang: "hi" }}
        evidence={null}
        onFollowUp={() => {}}
      />,
    );
    expect(screen.getByTestId("translated")).toHaveTextContent(
      "Translated from English",
    );
    unmount();
    renderWithIntl(
      <AnswerCard answer={base} evidence={null} onFollowUp={() => {}} />,
    );
    expect(screen.queryByTestId("translated")).toBeNull();
  });

  it("shows fact-checks attributed to the fact-checker, marking related claims", () => {
    renderWithIntl(
      <AnswerCard answer={base} evidence={null} onFollowUp={() => {}} />,
    );
    const list = within(screen.getByTestId("fact-checks"));
    expect(list.getByText("Checked by BOOM")).toBeInTheDocument();
    expect(list.getByText("Rating: False")).toBeInTheDocument(); // the fact-checker's own wording
    expect(list.getAllByText("About a related claim")).toHaveLength(1);
    expect(
      list.getAllByRole("link", { name: /Read the fact-check/ })[0],
    ).toHaveAttribute("target", "_blank");
  });
});
