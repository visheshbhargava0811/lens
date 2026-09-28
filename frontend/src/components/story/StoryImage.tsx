"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import type { StoryCard as StoryCardData } from "@/lib/api/types";
import { cn } from "@/lib/utils";
import { safeUrl } from "@/lib/safe-url";

type Variant = "hero" | "standard" | "compact";

const frame: Record<Variant, string> = {
  hero: "aspect-[16/9]",
  standard: "aspect-[3/2]",
  compact: "aspect-square w-20 shrink-0 md:w-24",
};

/**
 * The outlet's own feed thumbnail, hotlinked (ADR-0034): the browser loads it straight from the outlet,
 * so Lens never fetches, caches or re-hosts it, and it is always credited. Only sources with
 * image_policy=hotlink ever send one (docs/09). Missing or broken: a designed text tile, never a blank.
 */
export function StoryImage({
  story,
  variant,
}: {
  story: StoryCardData;
  variant: Variant;
}) {
  const t = useTranslations();
  const [broken, setBroken] = useState(false);
  const image = broken ? null : story.image;

  if (!image) {
    // Compact rows and heroes read better as text than as a large empty block; grid cards keep a tile.
    if (variant !== "standard") return null;
    return (
      <div
        aria-hidden
        data-testid="story-tile"
        className={cn(
          frame[variant],
          "flex flex-col justify-end rounded-card bg-surface p-4 pattern-light-hatch",
        )}
      >
        <span className="text-xs font-bold uppercase tracking-wide text-ink-muted">
          {story.topic ? t(`topics.${story.topic}`) : t("topics.top")}
        </span>
        <span className="text-sm font-bold text-ink">
          {t("coverage.sources", { count: story.counts.sources })}
        </span>
      </div>
    );
  }
  return (
    <figure
      className={cn(
        frame[variant],
        "relative overflow-hidden rounded-card bg-surface",
      )}
      data-testid="story-image"
    >
      {/* eslint-disable-next-line @next/next/no-img-element -- hotlinked on purpose: the Next image optimizer would fetch and cache it on our server */}
      <img
        src={safeUrl(image.url)}
        alt=""
        loading={variant === "hero" ? "eager" : "lazy"}
        decoding="async"
        referrerPolicy="no-referrer"
        onError={() => setBroken(true)}
        className="size-full object-cover"
      />
      {variant !== "compact" && (
        <figcaption className="absolute bottom-0 end-0 rounded-tl-card bg-ink/70 px-2 py-0.5 text-[11px] text-paper">
          {t("story.imageCredit", { source: image.source_name })}
        </figcaption>
      )}
    </figure>
  );
}
