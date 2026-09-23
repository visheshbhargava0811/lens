import { getTranslations } from "next-intl/server";

import { getMethodology } from "@/lib/api/client";

const SECTIONS = [
  "coverage",
  "bias",
  "factuality",
  "ownership",
  "blindspots",
  "summaries",
  "languages",
  "limits",
  "corrections",
] as const;

/** Prose from the translated messages; live thresholds and raters from `/methodology` (ADR-0018). */
export default async function MethodologyPage() {
  const t = await getTranslations("methodology");
  const m = await getMethodology();
  const pct = (share: number) => Math.round(share * 100);
  return (
    <div className="grid gap-12 lg:grid-cols-[240px_minmax(0,1fr)]">
      <nav aria-label={t("heading")} className="min-w-0 lg:sticky lg:top-[7.75rem] lg:self-start">
        <ul className="flex gap-2 overflow-x-auto pb-1 text-sm lg:flex-col lg:gap-0">
          {SECTIONS.map((key) => (
            <li key={key} className="shrink-0">
              <a href={`#${key}`} className="inline-block rounded-chip bg-surface px-3 py-1.5 font-bold text-ink-muted hover:text-ink lg:block lg:bg-transparent lg:px-0 lg:py-1.5 lg:hover:underline">
                {t(`sections.${key}.title`)}
              </a>
            </li>
          ))}
        </ul>
      </nav>
      <div className="min-w-0 max-w-[68ch]">
        <h1 className="text-4xl md:text-5xl">{t("heading")}</h1>
        <p className="mt-4 text-xl">{t("intro")}</p>
        <p className="mt-6 rounded-card bg-flag-bg px-4 py-3 text-sm font-medium text-flag-ink">{t("draft")}</p>
        {SECTIONS.map((key) => (
          <section key={key} id={key} aria-labelledby={`${key}-title`} className="mt-12 scroll-mt-40 border-t border-ink/15 pt-6">
            <h2 id={`${key}-title`} className="text-2xl">
              {t(`sections.${key}.title`)}
            </h2>
            <p className="mt-3 text-[1.0625rem]">{t(`sections.${key}.body`)}</p>
          </section>
        ))}
        <section id="settings" aria-labelledby="settings-title" className="mt-12 scroll-mt-40 border-t border-ink/15 pt-6">
          <h2 id="settings-title" className="text-2xl">
            {t("current.heading")}
          </h2>
          {m ? (
            <>
              <p className="mt-3 text-sm text-ink-muted">{t("current.note")}</p>
              <ul className="mt-4 list-disc space-y-2 ps-5 text-[1.0625rem]">
                <li>{t("current.minSourcesForBar", { n: m.min_sources_for_bar })}</li>
                <li>{t("current.feedMinSources", { n: m.feed_min_sources })}</li>
                <li>{t("current.biasBlindspot", { pct: pct(m.blindspot_bias_share), n: m.min_sources_for_blindspot })}</li>
                <li>{t("current.languageBlindspot", { pct: pct(m.blindspot_language_share), n: m.min_sources_for_blindspot })}</li>
              </ul>
              <h3 className="mt-6 text-lg">{t("current.raters")}</h3>
              {m.raters.length ? (
                <ul className="mt-2 space-y-2 text-[1.0625rem]">
                  {m.raters.map((r) => (
                    <li key={`${r.rater}-${r.dimension}`}>
                      {t("current.rater", { rater: r.rater, count: r.sources_rated, dimension: r.dimension })}{" "}
                      <a href={r.method_url} className="font-bold underline" rel="noopener noreferrer" target="_blank">
                        {t("current.method")}
                      </a>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="mt-2">{t("current.noRaters")}</p>
              )}
            </>
          ) : (
            <p className="mt-3">{t("current.unavailable")}</p>
          )}
        </section>
      </div>
    </div>
  );
}
