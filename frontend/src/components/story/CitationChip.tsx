"use client";

import { useTranslations } from "next-intl";

import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import type { ArticleRow, Citation } from "@/lib/api/types";

import { showArticle } from "./events";
import { safeUrl } from "@/lib/safe-url";

export type CitedArticle = Pick<ArticleRow, "id" | "headline" | "headline_lang" | "url"> & {
  sourceName: string;
  sourceLanguage: string;
};

/** `[n]` button. Opens a popover with the source, headline and link, and can reveal the row in the list. */
export function CitationChip({ citation, article }: { citation: Citation; article?: CitedArticle }) {
  const t = useTranslations("citation");
  const tSources = useTranslations("sources");
  return (
    <Popover>
      <PopoverTrigger
        aria-label={t("label", { n: citation.n, source: citation.source_name })}
        data-testid="citation-chip"
        data-article-id={citation.article_id}
        className="mx-0.5 inline-flex h-5 min-w-5 items-center justify-center rounded-[2px] bg-surface px-1 align-[0.15em] text-[11px] font-bold tabular-nums text-ink hover:bg-ink hover:text-paper data-[popup-open]:bg-ink data-[popup-open]:text-paper"
      >
        {citation.n}
      </PopoverTrigger>
      <PopoverContent
        align="start"
        className="w-80"
        data-testid="citation-popover"
        aria-label={t("label", { n: citation.n, source: citation.source_name })}
      >
        <p className="text-xs font-medium text-ink-muted" lang={article?.sourceLanguage}>
          {citation.source_name}
        </p>
        {article && (
          <p lang={article.headline_lang} className="font-medium" style={{ lineHeight: "var(--leading-headline)" }}>
            {article.headline}
          </p>
        )}
        <p className="text-xs text-ink-muted">{t("noPassage")}</p>
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1">
          <button
            type="button"
            onClick={() => showArticle(citation.article_id)}
            className="text-sm font-bold underline decoration-ink/40 hover:decoration-ink"
          >
            {t("showInList")}
          </button>
          {article && (
            <a
              href={safeUrl(article.url)}
              target="_blank"
              rel="noopener noreferrer"
              className="text-sm font-bold underline decoration-ink/40 hover:decoration-ink"
            >
              {t("readAt", { source: citation.source_name })}
              <span className="sr-only"> {tSources("newTab")}</span>
            </a>
          )}
        </div>
      </PopoverContent>
    </Popover>
  );
}
