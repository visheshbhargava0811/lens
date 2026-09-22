import Link from "next/link";
import { useTranslations } from "next-intl";

import { CoverageBar } from "@/components/coverage/CoverageBar";
import type { StoryCard as StoryCardData } from "@/lib/api/types";
import { segmentsFromCoverage } from "@/lib/coverage";
import { cn } from "@/lib/utils";

import { FlagChip } from "./FlagChip";
import { StoryMeta } from "./StoryMeta";

type Variant = "hero" | "standard" | "compact";

/**
 * The whole card is one link (stretched from the headline). Only the coverage bar,
 * its methodology link and the flag chip sit above it and stay interactive.
 */
export function StoryCard({
  story,
  variant = "standard",
  strongBar = false,
  headingLevel = 3,
}: {
  story: StoryCardData;
  variant?: Variant;
  strongBar?: boolean;
  headingLevel?: 2 | 3;
}) {
  const t = useTranslations();
  const H = `h${headingLevel}` as const;
  const labelledBar = variant === "hero" || strongBar;
  const lead = leadingShare(story, t);

  return (
    <article
      data-testid={`story-card-${variant}`}
      className={cn(
        "group relative flex flex-col",
        variant === "hero" && "gap-5",
        variant === "standard" && "gap-3",
        variant === "compact" && "gap-2 py-4",
      )}
    >
      <H
        lang={story.headline_lang}
        className={cn(
          variant === "hero" && "text-[2rem] md:text-[2.75rem]",
          variant === "standard" && "text-xl",
          variant === "compact" && "text-base font-bold",
        )}
      >
        <Link href={`/story/${story.slug}`} className="headline-link after:absolute after:inset-0 after:content-['']">
          {story.headline}
        </Link>
      </H>

      {variant === "hero" && story.summary_preview && (
        <p lang={story.headline_lang} className="line-clamp-3 max-w-[62ch] text-lg text-ink-muted">
          {story.summary_preview}
        </p>
      )}

      <CoverageBar
        coverage={story.coverage}
        sourceCount={story.counts.sources}
        size={labelledBar ? (variant === "hero" ? "lg" : "md") : "sm"}
        showMeta
        summary={labelledBar ? undefined : lead}
      />

      <StoryMeta
        story={story}
        showStatus={variant === "hero"}
        maxLanguages={variant === "compact" ? 0 : variant === "hero" ? 5 : 2}
      />

      {story.blindspot && <FlagChip blindspot={story.blindspot} className="self-start" />}
    </article>
  );
}

/** "56% critical of the government": the largest classified share, for small bars. */
function leadingShare(story: StoryCardData, t: ReturnType<typeof useTranslations>): string | undefined {
  const segments = segmentsFromCoverage(story.coverage).filter((s) => s.key !== "unclassified" && s.sources > 0);
  if (segments.length === 0) return undefined;
  const top = segments.reduce((a, b) => (b.sources > a.sources ? b : a));
  return t("coverage.dominant", { pct: top.pct, phrase: t(`stance.phrase.${top.key}`) });
}
