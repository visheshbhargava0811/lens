import { getTranslations } from "next-intl/server";

const SECTIONS = [
  "coverage",
  "stance",
  "factuality",
  "ownership",
  "blindspots",
  "summaries",
  "languages",
  "limits",
  "corrections",
] as const;

/** Static placeholder (Phase 1B). Rater list, validation results and changelog land before launch. */
export default async function MethodologyPage() {
  const t = await getTranslations("methodology");
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
      </div>
    </div>
  );
}
