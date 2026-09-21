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
    <div className="grid gap-10 lg:grid-cols-[220px_minmax(0,1fr)]">
      <nav aria-label={t("heading")} className="min-w-0 lg:sticky lg:top-32 lg:self-start">
        <ul className="flex gap-2 overflow-x-auto pb-1 text-sm lg:flex-col lg:gap-1">
          {SECTIONS.map((key) => (
            <li key={key} className="shrink-0">
              <a href={`#${key}`} className="inline-block rounded-control px-2 py-1 text-ink-muted hover:bg-surface hover:text-ink">
                {t(`sections.${key}.title`)}
              </a>
            </li>
          ))}
        </ul>
      </nav>
      <div className="min-w-0 max-w-[68ch]">
        <h1 className="text-3xl">{t("heading")}</h1>
        <p className="mt-3 text-lg">{t("intro")}</p>
        <p className="mt-4 rounded-control bg-flag-bg px-3 py-2 text-sm text-flag-ink">{t("draft")}</p>
        {SECTIONS.map((key) => (
          <section key={key} id={key} aria-labelledby={`${key}-title`} className="mt-10 scroll-mt-32">
            <h2 id={`${key}-title`} className="text-2xl">
              {t(`sections.${key}.title`)}
            </h2>
            <p className="mt-2">{t(`sections.${key}.body`)}</p>
          </section>
        ))}
      </div>
    </div>
  );
}
