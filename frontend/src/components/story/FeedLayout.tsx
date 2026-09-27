import { EyeOff } from "lucide-react";
import Link from "next/link";
import { useTranslations } from "next-intl";

import type { Page, StoryCard as StoryCardData } from "@/lib/api/types";

import { EmptyState } from "../states/EmptyState";
import { FeedMore } from "./FeedMore";
import { StoryCard } from "./StoryCard";

type Props = {
  heading: string;
  page: Page<StoryCardData>;
  emptyMessage: string;
  blindspots: StoryCardData[];
  topicSlugs: { slug: string; name: string }[];
  topic?: string;
};

/** Lead story beside the rail, then a full-width ruled grid. On mobile the rail follows the lead. */
export function FeedLayout({ heading, page, emptyMessage, blindspots, topicSlugs, topic }: Props) {
  const t = useTranslations("home");
  const tt = useTranslations("topics");
  // Lead with the newest story that has enough sources for a coverage bar; the newest story may be a
  // two-source item that leaves the lead slot bare. Falls back to the newest when none qualifies.
  const hero = page.items.find((s) => s.coverage.available) ?? page.items[0];
  const rest = page.items.filter((s) => s !== hero);
  const rail = (
    <aside className="min-w-0">
      {blindspots.length > 0 && (
        <section aria-labelledby="rail-blindspots" className="rounded-card bg-surface p-5">
          <h2 id="rail-blindspots" className="flex items-center gap-2 text-2xl">
            <EyeOff aria-hidden className="size-6" strokeWidth={2.5} />
            {t("railBlindspots")}
          </h2>
          <p className="mt-1.5 text-sm text-ink-muted">{t("railBlindspotsIntro")}</p>
          <div className="mt-2 flex snap-x gap-4 overflow-x-auto pb-1 lg:block lg:divide-y lg:divide-ink/15 lg:overflow-visible">
            {blindspots.slice(0, 2).map((s) => (
              <div key={s.id} className="w-72 shrink-0 snap-start lg:w-auto">
                <StoryCard story={s} variant="compact" />
              </div>
            ))}
          </div>
          <Link href="/blindspot" className="mt-3 inline-block text-sm font-bold underline decoration-ink/40 hover:decoration-ink">
            {t("seeAllBlindspots")}
          </Link>
        </section>
      )}
    </aside>
  );

  const topicsBlock = topicSlugs.length > 0 && (
    <section aria-labelledby="rail-topics" className="mt-10 border-t border-ink/15 pt-5">
      <h2 id="rail-topics" className="text-lg">
        {t("railTopics")}
      </h2>
      <ul className="mt-3 flex flex-wrap gap-2">
        {topicSlugs.map((tp) => (
          <li key={tp.slug}>
            <Link
              href={`/topic/${tp.slug}`}
              className="inline-flex h-8 items-center rounded-chip bg-surface px-3 text-sm font-bold hover:bg-line"
            >
              {tt.has(tp.slug) ? tt(tp.slug) : tp.name}
            </Link>
          </li>
        ))}
      </ul>
    </section>
  );

  return (
    <div>
      <h1 className="sr-only">{heading}</h1>
      {!hero ? (
        <div className="grid gap-x-12 gap-y-12 lg:grid-cols-[minmax(0,1fr)_340px]">
          <div className="min-w-0">
            <EmptyState>{emptyMessage}</EmptyState>
            {topicsBlock}
          </div>
          {rail}
        </div>
      ) : (
        <>
          <div className="grid gap-x-12 gap-y-10 lg:grid-cols-[minmax(0,1fr)_340px]">
            <div className="min-w-0">
              <section aria-label={t("hero")}>
                <StoryCard story={hero} variant="hero" headingLevel={2} />
              </section>
              {topicsBlock}
            </div>
            {rail}
          </div>
          {rest.length > 0 && (
            <section aria-labelledby="more-heading" className="mt-12 border-t-[3px] border-ink pt-5">
              <h2 id="more-heading" className="text-2xl">
                {t("more")}
              </h2>
              <FeedGrid stories={rest} />
            </section>
          )}
          <div className="mt-2">
            <FeedMore initialCursor={page.next_cursor} topic={topic} />
          </div>
        </>
      )}
    </div>
  );
}

/** Ruled grid of standard cards: two columns on tablets, three on desktop. */
export function FeedGrid({ stories }: { stories: StoryCardData[] }) {
  return (
    <div className="grid gap-x-10 sm:grid-cols-2 lg:grid-cols-3">
      {stories.map((s) => (
        <div key={s.id} className="border-b border-ink/15 py-5">
          <StoryCard story={s} />
        </div>
      ))}
    </div>
  );
}
