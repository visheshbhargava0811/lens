import { useFormatter, useLocale, useNow, useTranslations } from "next-intl";

import { stanceFill } from "@/components/coverage/stance-style";
import type { ArticleRow as ArticleRowData } from "@/lib/api/types";
import { articleBucket } from "@/lib/coverage";
import { languageName } from "@/lib/format";
import { cn } from "@/lib/utils";

export const articleDomId = (id: string) => `article-${id}`;

export function ArticleRow({ article, highlighted = false }: { article: ArticleRowData; highlighted?: boolean }) {
  const t = useTranslations();
  const format = useFormatter();
  const now = useNow();
  const locale = useLocale();
  const bucket = articleBucket(article.stance);
  const stanceLabel =
    article.stance.value === "not_applicable"
      ? t("stance.label.not_applicable")
      : t(`stance.label.${bucket}`, { target: article.stance.target });
  const confidence = t(`confidence.${article.stance.confidence}`);

  return (
    <li
      id={articleDomId(article.id)}
      tabIndex={-1}
      data-testid="article-row"
      data-highlighted={highlighted || undefined}
      className={cn(
        "scroll-mt-32 border-b py-4 outline-none transition-colors last:border-b-0",
        highlighted && "rounded-control bg-flag-bg/60 px-3",
      )}
    >
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm">
        <span className="font-medium" lang={article.source.language}>
          {article.source.name}
        </span>
        <span className="rounded-chip bg-surface px-2 py-0.5 text-xs text-ink-muted">
          {languageName(article.source.language, locale)}
        </span>
        <time dateTime={article.published_at} className="text-xs text-ink-muted">
          {format.relativeTime(new Date(article.published_at), now)}
        </time>
      </div>

      <p lang={article.headline_lang} className="mt-1.5 text-lg font-medium" style={{ lineHeight: "var(--leading-headline)" }}>
        {article.headline}
      </p>

      <ul className="mt-2 flex flex-wrap gap-2 text-xs">
        <li className="inline-flex items-center gap-1.5 rounded-chip border px-2 py-0.5">
          <span aria-hidden className={cn("size-2.5 rounded-full", stanceFill[bucket])} />
          {t("sources.stanceConfidence", { label: stanceLabel, confidence })}
        </li>
        <li className="rounded-chip border px-2 py-0.5">
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
        <li className="rounded-chip border px-2 py-0.5">
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
          className="font-medium text-link underline-offset-2 hover:underline"
        >
          {t("sources.readAt", { source: article.source.name })}
          <span className="sr-only"> {t("sources.newTab")}</span>
        </a>
      </div>
    </li>
  );
}
