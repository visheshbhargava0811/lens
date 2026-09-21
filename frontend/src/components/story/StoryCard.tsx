import Link from "next/link";
import { useTranslations } from "next-intl";

import { CoverageBar } from "@/components/coverage/CoverageBar";
import { StanceLegend } from "@/components/coverage/StanceLegend";
import type { StoryCard as StoryCardData } from "@/lib/api/types";
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
  const t = useTranslations("status");
  const H = `h${headingLevel}` as const;
  const developing = story.status === "developing";

  return (
    <article
      data-testid={`story-card-${variant}`}
      className={cn(
        "group relative flex flex-col",
        variant === "hero" && "gap-4",
        variant === "standard" && "gap-3 rounded-card border p-4 hover:border-ink-muted/40",
        variant === "compact" && "gap-2 border-b py-3 last:border-b-0",
      )}
    >
      {variant === "hero" && developing && <p className="text-sm font-medium">{t("developing")}</p>}
      <H
        lang={story.headline_lang}
        className={cn(
          variant === "hero" && "text-3xl md:text-4xl",
          variant === "standard" && "text-xl",
          variant === "compact" && "text-base font-medium",
        )}
      >
        <Link
          href={`/story/${story.slug}`}
          className="after:absolute after:inset-0 after:rounded-card after:content-[''] group-hover:underline decoration-1 underline-offset-4"
        >
          {story.headline}
        </Link>
      </H>

      <CoverageBar
        coverage={story.coverage}
        sourceCount={story.counts.sources}
        size={variant === "hero" || strongBar ? "md" : "sm"}
        showMeta={variant !== "compact"}
      />
      {variant === "hero" && <StanceLegend coverage={story.coverage} compact />}

      <StoryMeta story={story} maxLanguages={variant === "compact" ? 0 : variant === "hero" ? 5 : 2} />

      {story.blindspot && <FlagChip blindspot={story.blindspot} className="self-start" />}

      {variant === "hero" && story.summary_preview && (
        <p lang={story.headline_lang} className="line-clamp-2 max-w-[68ch] text-ink-muted">
          {story.summary_preview}
        </p>
      )}
    </article>
  );
}
