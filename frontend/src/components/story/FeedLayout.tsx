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

/** Hero, 2-column grid, right rail (desktop). On mobile the rail follows the feed. */
export function FeedLayout({ heading, page, emptyMessage, blindspots, topicSlugs, topic }: Props) {
  const t = useTranslations("home");
  const [hero, ...rest] = page.items;
  return (
    <div className="grid gap-10 lg:grid-cols-[minmax(0,1fr)_320px]">
      <div className="min-w-0">
        <h1 className="sr-only">{heading}</h1>
        {!hero ? (
          <EmptyState>{emptyMessage}</EmptyState>
        ) : (
          <>
            <section aria-label={t("hero")} className="border-b pb-8">
              <StoryCard story={hero} variant="hero" headingLevel={2} />
            </section>
            {rest.length > 0 && (
              <section aria-label={t("more")} className="mt-8 grid gap-4 sm:grid-cols-2">
                {rest.map((s) => (
                  <StoryCard key={s.id} story={s} />
                ))}
              </section>
            )}
            <div className="mt-4">
              <FeedMore initialCursor={page.next_cursor} topic={topic} />
            </div>
          </>
        )}
      </div>

      <aside className="min-w-0 space-y-8 lg:sticky lg:top-32 lg:self-start">
        {blindspots.length > 0 && (
          <section aria-labelledby="rail-blindspots">
            <h2 id="rail-blindspots" className="text-lg">
              {t("railBlindspots")}
            </h2>
            <div className="mt-2 flex snap-x gap-4 overflow-x-auto pb-2 lg:block lg:overflow-visible">
              {blindspots.slice(0, 3).map((s) => (
                <div key={s.id} className="w-72 shrink-0 snap-start lg:w-auto">
                  <StoryCard story={s} variant="compact" />
                </div>
              ))}
            </div>
            <Link href="/blindspot" className="mt-1 inline-block text-sm font-medium text-link hover:underline">
              {t("seeAllBlindspots")}
            </Link>
          </section>
        )}
        {topicSlugs.length > 0 && (
          <section aria-labelledby="rail-topics">
            <h2 id="rail-topics" className="text-lg">
              {t("railTopics")}
            </h2>
            <ul className="mt-3 flex flex-wrap gap-2">
              {topicSlugs.map((tp) => (
                <li key={tp.slug}>
                  <Link
                    href={`/topic/${tp.slug}`}
                    className="inline-flex h-8 items-center rounded-chip bg-surface px-3 text-sm font-medium hover:bg-line"
                  >
                    {tp.name}
                  </Link>
                </li>
              ))}
            </ul>
          </section>
        )}
      </aside>
    </div>
  );
}
