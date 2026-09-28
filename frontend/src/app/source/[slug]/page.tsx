import { notFound } from "next/navigation";
import { getFormatter, getLocale, getTranslations } from "next-intl/server";

import { MethodologyLink } from "@/components/coverage/MethodologyLink";
import { FeedGrid } from "@/components/story/FeedLayout";
import { getSource } from "@/lib/api/client";
import { languageName } from "@/lib/format";
import { safeUrl } from "@/lib/safe-url";

/** Source page (docs/10 §5): ownership and every rating with its provenance, then recent stories. */
export default async function SourcePage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  const data = await getSource(slug);
  if (!data) notFound();

  const t = await getTranslations("source");
  const tc = await getTranslations("confidence");
  const locale = await getLocale();
  const format = await getFormatter();
  const { source, ownership, ratings, recent_stories } = data;
  const date = (iso: string) => format.dateTime(new Date(iso), { dateStyle: "medium" });
  const dimension = (d: string) => (d === "bias" || d === "factuality" ? t(`dimension.${d}`) : t("dimension.other"));
  const extLink = "font-bold underline decoration-ink/40 hover:decoration-ink";

  return (
    <div className="space-y-12">
      <header className="border-b border-ink/15 pb-8">
        <h1 className="text-4xl md:text-5xl">{source.name}</h1>
        <dl className="mt-4 flex flex-wrap gap-x-6 gap-y-1 text-sm">
          <div className="flex gap-1.5">
            <dt className="text-ink-muted">{t("languages")}</dt>
            <dd className="font-bold">{source.languages.map((l) => languageName(l, locale)).join(", ")}</dd>
          </div>
          <div className="flex gap-1.5">
            <dt className="text-ink-muted">{t("region")}</dt>
            <dd className="font-bold">{source.region === "national" || !source.region ? t("national") : source.region}</dd>
          </div>
          {source.is_wire && <dd className="font-bold">{t("wire")}</dd>}
        </dl>
        <p className="mt-3 max-w-[68ch] text-sm text-ink-muted">{t(`license.${source.license_mode}`)}</p>
        <a href={safeUrl(source.homepage_url)} target="_blank" rel="noopener noreferrer" className={`mt-3 inline-block text-sm ${extLink}`}>
          {t("homepage", { name: source.name })}
        </a>
      </header>

      <div className="grid gap-8 md:grid-cols-2">
        <section aria-labelledby="ratings-title" className="rounded-card bg-surface p-5">
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <h2 id="ratings-title" className="text-xl">
              {t("ratings")}
            </h2>
            <MethodologyLink href={data.methodology_url}>{t("about")}</MethodologyLink>
          </div>
          {ratings.length === 0 ? (
            <p className="mt-3">{t("noRatings")}</p>
          ) : (
            <ul className="mt-3 divide-y divide-ink/10">
              {ratings.map((r) => (
                <li key={`${r.dimension}-${r.rater}-${r.retrieved_at}`} className="py-3" data-testid="source-rating">
                  <p className="text-xs font-bold uppercase tracking-wide text-ink-muted">{dimension(r.dimension)}</p>
                  <p className="mt-1 font-bold">{t("rating", { rater: r.rater, value: r.value })}</p>
                  <p className="mt-1 flex flex-wrap gap-x-3 gap-y-1 text-xs text-ink-muted">
                    <span>{t("confidence", { level: tc(r.confidence) })}</span>
                    <span>{t("retrieved", { date: date(r.retrieved_at) })}</span>
                    <a href={safeUrl(r.method_url)} target={r.method_url.startsWith("/") ? undefined : "_blank"} rel="noopener noreferrer" className={extLink}>
                      {t("method")}
                    </a>
                    {r.evidence_url && (
                      <a href={safeUrl(r.evidence_url)} target="_blank" rel="noopener noreferrer" className={extLink}>
                        {t("evidence")}
                      </a>
                    )}
                  </p>
                </li>
              ))}
              {(["bias", "factuality"] as const)
                .filter((d) => !ratings.some((r) => r.dimension === d))
                .map((d) => (
                  <li key={d} className="py-3" data-testid="source-rating-missing">
                    <p className="text-xs font-bold uppercase tracking-wide text-ink-muted">{dimension(d)}</p>
                    <p className="mt-1">{t("notRatedDim")}</p>
                  </li>
                ))}
            </ul>
          )}
        </section>

        <section aria-labelledby="ownership-title" className="rounded-card bg-surface p-5">
          <h2 id="ownership-title" className="text-xl">
            {t("ownership")}
          </h2>
          {ownership.length === 0 ? (
            <p className="mt-3">{t("noOwnership")}</p>
          ) : (
            <ul className="mt-3 divide-y divide-ink/10">
              {ownership.map((o) => (
                <li key={`${o.owner_name}-${o.retrieved_at}`} className="py-3" data-testid="source-owner">
                  <p className="font-bold">{t("owner", { owner: o.owner_name })}</p>
                  {o.parent_group && <p className="mt-0.5 text-sm">{t("group", { group: o.parent_group })}</p>}
                  <p className="mt-1 flex flex-wrap gap-x-3 gap-y-1 text-xs text-ink-muted">
                    <span>{t("confidence", { level: tc(o.confidence) })}</span>
                    <span>{t("retrieved", { date: date(o.retrieved_at) })}</span>
                    <a href={safeUrl(o.evidence_url)} target="_blank" rel="noopener noreferrer" className={extLink}>
                      {t("evidence")}
                    </a>
                  </p>
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>

      <section aria-labelledby="recent-title" className="border-t-[3px] border-ink pt-4">
        <h2 id="recent-title" className="text-2xl">
          {t("recent")}
        </h2>
        {recent_stories.length === 0 ? <p className="mt-3">{t("noRecent")}</p> : <FeedGrid stories={recent_stories} />}
      </section>
    </div>
  );
}
