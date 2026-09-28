import { useTranslations } from "next-intl";

import type { FactCheck } from "@/lib/api/types";

/**
 * Fact-checks published by independent fact-checkers (docs/13): their claim, their rating wording, their
 * name and link. Lens never presents a match as its own verdict; a `related` match is labeled as such.
 */
export function FactCheckList({
  items,
  panel = "rounded-card bg-surface p-5",
}: {
  items: FactCheck[];
  panel?: string;
}) {
  const t = useTranslations("story");
  return (
    <>
      <p className="mt-1 text-sm text-ink-muted">{t("factCheckIntro")}</p>
      <ul className="mt-3 space-y-3">
        {items.map((fc) => (
          <li key={fc.url} className={panel}>
            {fc.match === "related" && (
              <p className="mb-1 text-xs font-bold tracking-wide text-ink-muted uppercase">
                {t("factCheckRelated")}
              </p>
            )}
            <p className="font-medium">{fc.claim}</p>
            <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-sm">
              <span
                className="rounded-chip bg-card px-2 py-0.5 font-bold"
                data-rating={fc.rating_normalized}
              >
                {t("factCheckRating", { rating: fc.rating })}
              </span>
              <span className="text-ink-muted">
                {t("factCheckBy", { checker: fc.fact_checker })}
              </span>
              <a
                href={fc.url}
                target="_blank"
                rel="noopener noreferrer"
                className="font-bold underline decoration-ink/40 hover:decoration-ink"
              >
                {t("readFactCheck")}
                <span className="sr-only"> {t("newTab")}</span>
              </a>
            </div>
          </li>
        ))}
      </ul>
    </>
  );
}
