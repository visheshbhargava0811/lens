import { ShieldCheck } from "lucide-react";
import { useTranslations } from "next-intl";

import type { CitedSentence, StorySummary } from "@/lib/api/types";

import { CitationChip, type CitedArticle } from "./CitationChip";

export function CitedText({
  sentences,
  lang,
  articles,
  as = "p",
}: {
  sentences: CitedSentence[];
  lang: string;
  articles: Record<string, CitedArticle>;
  as?: "p" | "li";
}) {
  const Tag = as;
  return sentences.map((s, i) => (
    <Tag key={i} lang={lang}>
      {s.text}
      {s.citations.map((c) => (
        <CitationChip key={c.n} citation={c} article={articles[c.article_id]} />
      ))}
    </Tag>
  ));
}

/** Cited summary sentences. "Verified against sources" appears only when verified is true. */
export function SummaryBlock({
  summary,
  articles,
}: {
  summary: StorySummary | null;
  articles: Record<string, CitedArticle>;
}) {
  const t = useTranslations("summary");
  return (
    <section aria-labelledby="summary-heading">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
        <h2 id="summary-heading" className="text-2xl">
          {t("title")}
        </h2>
        {summary?.verified && (
          <span className="inline-flex items-center gap-1 text-sm font-medium text-stance-supportive" data-testid="verified">
            <ShieldCheck aria-hidden className="size-4" />
            {t("verified")}
          </span>
        )}
      </div>
      {summary && summary.sentences.length > 0 ? (
        <div className="mt-3 max-w-[68ch] space-y-2 text-lg">
          <CitedText sentences={summary.sentences} lang={summary.lang} articles={articles} />
        </div>
      ) : (
        <p className="mt-3 rounded-control bg-surface px-3 py-3 text-ink-muted">{t("unavailable")}</p>
      )}
    </section>
  );
}
