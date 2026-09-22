import { notFound } from "next/navigation";
import { getFormatter, getLocale, getNow, getTranslations } from "next-intl/server";

import { CoverageBar } from "@/components/coverage/CoverageBar";
import { FactualityMeter } from "@/components/coverage/FactualityMeter";
import { OwnershipTags } from "@/components/coverage/OwnershipTags";
import { StanceLegend } from "@/components/coverage/StanceLegend";
import type { CitedArticle } from "@/components/story/CitationChip";
import { FlagChip } from "@/components/story/FlagChip";
import { SourceList } from "@/components/story/SourceList";
import { CitedText, SummaryBlock } from "@/components/story/SummaryBlock";
import { getStory, getStoryArticles } from "@/lib/api/client";
import type { CitedSentence } from "@/lib/api/types";
import { dominantTarget, segmentsFromCoverage } from "@/lib/coverage";

export default async function StoryPage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  const locale = await getLocale();
  const detail = await getStory(slug, locale);
  if (!detail) notFound();

  const articles = await getStoryArticles(detail.story.id);
  const t = await getTranslations();
  const format = await getFormatter();
  const now = await getNow();
  const { story, summary } = detail;

  const cited: Record<string, CitedArticle> = Object.fromEntries(
    articles.items.map((a) => [
      a.id,
      {
        id: a.id,
        headline: a.headline,
        headline_lang: a.headline_lang,
        url: a.url,
        sourceName: a.source.name,
        sourceLanguage: a.source.language,
      },
    ]),
  );
  const lang = summary?.lang ?? story.headline_lang;
  const target = dominantTarget(articles.items);

  const panel = "rounded-card bg-surface p-5";
  const segments = segmentsFromCoverage(story.coverage);
  const updated = format.relativeTime(new Date(story.updated_at), now);
  const coveragePanel = (id: string) => (
    <section aria-labelledby={id} className={panel}>
      <h2 id={id} className="text-xl">
        {t("story.coverageDetails")}
      </h2>
      <dl className="mt-3 divide-y divide-ink/10 text-[0.9375rem]">
        <Row label={t("story.totalSources")} value={story.counts.sources} strong />
        {segments.map((s) => (
          <Row key={s.key} label={t(`stance.label.${s.key}`, { target })} value={s.sources} />
        ))}
        <Row label={t("story.lastUpdated")} value={updated} />
        <Row label={t("story.status")} value={t(`status.${story.status}`)} />
      </dl>
      <h3 className="mt-6 text-base">{t("story.distribution")}</h3>
      <CoverageBar
        coverage={story.coverage}
        sourceCount={story.counts.sources}
        size="lg"
        className="mt-2.5"
        showMeta={false}
      />
      <div className="mt-3">
        <StanceLegend coverage={story.coverage} target={target} />
      </div>
      {story.coverage.available && (
        <p className="mt-3 text-sm text-ink-muted">
          {t("coverage.confidence", { level: t(`confidence.${story.coverage.confidence}`) })}
        </p>
      )}
      <a
        href={story.coverage.methodology_url}
        className="mt-1 inline-block text-sm font-bold underline decoration-ink/40 hover:decoration-ink"
      >
        {t("coverage.howCalculated")}
      </a>
    </section>
  );

  return (
    <article className="grid gap-x-12 gap-y-8 lg:grid-cols-[minmax(0,1fr)_360px]">
      <div className="min-w-0 space-y-8">
        {/* 1. Headline (mobile and desktop: first) */}
        <header className="border-b border-ink/15 pb-7">
          <h1 lang={story.headline_lang} className="max-w-[26ch] text-[2.125rem] md:text-5xl">
            {story.headline}
          </h1>
          <div className="mt-4 flex flex-wrap items-center gap-x-4 gap-y-1 text-sm text-ink-muted">
            <span className="font-bold text-ink tabular-nums">{t("coverage.sources", { count: story.counts.sources })}</span>
            {story.status === "developing" && <span className="font-bold text-ink">{t("status.developing")}</span>}
            <time dateTime={story.updated_at}>{t("story.updated", { time: updated })}</time>
          </div>
          {story.blindspot && <FlagChip blindspot={story.blindspot} className="mt-4" />}
        </header>

        {/* Mobile and tablet: coverage card directly under the headline */}
        <div className="lg:hidden">{coveragePanel("coverage-heading-inline")}</div>

        <div className="space-y-10">
          {detail.limitations.length > 0 && (
            <div className="rounded-card bg-flag-bg px-4 py-3 text-sm font-medium text-flag-ink" data-testid="limitations">
              <h2 className="sr-only">{t("story.limitations")}</h2>
              <ul>
                {detail.limitations.map((l) => (
                  <li key={l}>{l}</li>
                ))}
              </ul>
            </div>
          )}

          <SummaryBlock summary={summary} articles={cited} />

          {summary && (summary.agreements.length > 0 || summary.disagreements.length > 0) && (
            <div className="grid gap-6 md:grid-cols-2">
              <SentenceList
                title={t("summary.agreements")}
                sentences={summary.agreements}
                lang={lang}
                articles={cited}
              />
              <SentenceList
                title={t("summary.disagreements")}
                sentences={summary.disagreements}
                lang={lang}
                articles={cited}
              />
            </div>
          )}
          {detail.framing_differences.length > 0 && (
            <SentenceList
              title={t("summary.framing")}
              sentences={detail.framing_differences}
              lang={lang}
              articles={cited}
            />
          )}

          <section aria-labelledby="factchecks-heading">
            <h2 id="factchecks-heading" className="border-t-[3px] border-ink pt-4 text-2xl">
              {t("story.factChecks")}
            </h2>
            {detail.fact_checks.length === 0 ? (
              <p className="mt-2 text-ink-muted">{t("story.noFactChecks")}</p>
            ) : (
              <ul className="mt-3 space-y-3">
                {detail.fact_checks.map((fc) => (
                  <li key={fc.url} className={panel}>
                    <p className="font-medium">{fc.claim}</p>
                    <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-sm">
                      <span className="rounded-chip bg-card px-2 py-0.5 font-bold">
                        {t("story.factCheckRating", { rating: fc.rating })}
                      </span>
                      <span className="text-ink-muted">{t("story.factCheckBy", { checker: fc.fact_checker })}</span>
                      <a
                        href={fc.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="font-bold underline decoration-ink/40 hover:decoration-ink"
                      >
                        {t("story.readFactCheck")}
                        <span className="sr-only"> {t("sources.newTab")}</span>
                      </a>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </section>

          <SourceList articles={articles.items} methodologyUrl={articles.methodology_url} />
        </div>
      </div>
      <aside className="min-w-0 space-y-5 lg:sticky lg:top-[7.75rem] lg:self-start">
        <div className="hidden lg:block">{coveragePanel("coverage-heading-rail")}</div>
        <section aria-labelledby="factuality-heading" className={panel}>
          <h2 id="factuality-heading" className="text-xl">
            {t("factuality.title")}
          </h2>
          <div className="mt-3">
            <FactualityMeter factuality={story.factuality} />
          </div>
        </section>
        <section aria-labelledby="ownership-heading" className={panel}>
          <h2 id="ownership-heading" className="text-xl">
            {t("ownership.title")}
          </h2>
          <div className="mt-3">
            <OwnershipTags ownership={detail.ownership} />
          </div>
        </section>
      </aside>
    </article>
  );
}

function SentenceList({
  title,
  sentences,
  lang,
  articles,
}: {
  title: string;
  sentences: CitedSentence[];
  lang: string;
  articles: Record<string, CitedArticle>;
}) {
  return (
    <section>
      <h2 className="text-xl">{title}</h2>
      <ul className="mt-2 list-disc space-y-1.5 ps-5 marker:text-ink-muted">
        <CitedText sentences={sentences} lang={lang} articles={articles} as="li" />
      </ul>
    </section>
  );
}

function Row({ label, value, strong = false }: { label: string; value: React.ReactNode; strong?: boolean }) {
  return (
    <div className="flex items-baseline justify-between gap-4 py-1.5">
      <dt>{label}</dt>
      <dd className={strong ? "text-lg font-extrabold tabular-nums" : "font-bold tabular-nums"}>{value}</dd>
    </div>
  );
}
