import Link from "next/link";
import { useFormatter, useLocale, useNow, useTranslations } from "next-intl";

import { biasFill } from "@/components/coverage/bias-style";
import type { ArticleRow as ArticleRowData } from "@/lib/api/types";
import { languageName } from "@/lib/format";
import { cn } from "@/lib/utils";

export const articleDomId = (id: string) => `article-${id}`;

export function ArticleRow({ article, highlighted = false }: { article: ArticleRowData; highlighted?: boolean }) {
  const t = useTranslations();
  const format = useFormatter();
  const now = useNow();
  const locale = useLocale();
  const bias = article.source_bias;

  return (
    <li
      id={articleDomId(article.id)}
      tabIndex={-1}
      data-testid="article-row"
      data-highlighted={highlighted || undefined}
      className={cn(
        "scroll-mt-40 border-b border-ink/15 py-5 outline-none transition-colors last:border-b-0",
        highlighted && "rounded-card bg-flag-bg/70 px-4",
      )}
    >
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm">
        <Link
          href={`/source/${article.source.id}`}
          className="font-extrabold hover:underline"
          lang={article.source.language}
        >
          {article.source.name}
        </Link>
        <span className="rounded-chip bg-surface px-1.5 py-0.5 text-xs font-medium text-ink-muted">
          {languageName(article.source.language, locale)}
        </span>
        <time dateTime={article.published_at} className="text-xs text-ink-muted">
          {format.relativeTime(new Date(article.published_at), now)}
        </time>
      </div>

      <p lang={article.headline_lang} className="mt-2 text-lg font-bold" style={{ lineHeight: "var(--leading-headline)" }}>
        {article.headline}
      </p>

      <ul className="mt-2.5 flex flex-wrap gap-1.5 text-xs font-medium">
        <li className="inline-flex items-center gap-1.5 rounded-chip bg-surface px-2 py-1">
          <span aria-hidden className={cn("size-3 rounded-[1px] ring-1 ring-ink/20", biasFill[article.bias])} />
          {bias ? (
            <a
              href={bias.method_url}
              target="_blank"
              rel="noopener noreferrer"
              title={t("factuality.ratedBy", { rater: bias.rater, confidence: t(`confidence.${bias.confidence}`) })}
              className="hover:underline"
            >
              {/* The rater's own wording, e.g. "Left-Center"; the swatch shows the bucket it counts in. */}
              {t("sources.biasRating", { value: bias.value })}
              <span className="sr-only">
                {" "}
                {t("factuality.ratedBy", { rater: bias.rater, confidence: t(`confidence.${bias.confidence}`) })}{" "}
                {t("sources.newTab")}
              </span>
            </a>
          ) : (
            t("sources.biasRating", { value: t("bias.label.unrated") })
          )}
        </li>
        <li className="rounded-chip bg-surface px-2 py-1">
          {article.source_factuality ? (
            <a
              href={article.source_factuality.method_url}
              target="_blank"
              rel="noopener noreferrer"
              title={t("factuality.ratedBy", {
                rater: article.source_factuality.rater,
                confidence: t(`confidence.${article.source_factuality.confidence}`),
              })}
              className="hover:underline"
            >
              {t("factuality.chip", { value: article.source_factuality.value })}
              <span className="sr-only">
                {" "}
                {t("factuality.ratedBy", {
                  rater: article.source_factuality.rater,
                  confidence: t(`confidence.${article.source_factuality.confidence}`),
                })}{" "}
                {t("sources.newTab")}
              </span>
            </a>
          ) : (
            t("factuality.chip", { value: t("factuality.notRated") })
          )}
        </li>
        <li className="rounded-chip bg-surface px-2 py-1">
          {article.source_ownership ? (
            <a
              href={article.source_ownership.evidence_url}
              target="_blank"
              rel="noopener noreferrer"
              className="hover:underline"
            >
              {t("ownership.owner", { owner: article.source_ownership.owner })}
              <span className="sr-only">
                {" "}
                {t("ownership.evidence", { owner: article.source_ownership.owner })} {t("sources.newTab")}
              </span>
            </a>
          ) : (
            t("ownership.owner", { owner: t("ownership.unknown") })
          )}
        </li>
      </ul>

      <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-sm">
        {article.analysis_depth !== "full_text" && (
          <span className="text-ink-muted">
            {article.analysis_depth === "headline_only" ? t("sources.depthHeadline") : t("sources.depthSnippet")}
          </span>
        )}
        {article.is_syndicated && <span className="text-ink-muted">{t("sources.syndicated")}</span>}
        {article.also_carried_by.length > 0 && (
          <span className="text-ink-muted" title={article.also_carried_by.join(", ")}>
            {t("sources.alsoCarried", { count: article.also_carried_by.length })}
          </span>
        )}
        <a
          href={article.url}
          target="_blank"
          rel="noopener noreferrer"
          className="font-bold underline decoration-ink/40 hover:decoration-ink"
        >
          {t("sources.readAt", { source: article.source.name })}
          <span className="sr-only"> {t("sources.newTab")}</span>
        </a>
      </div>
    </li>
  );
}
