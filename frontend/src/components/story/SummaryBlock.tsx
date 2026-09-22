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
          <span className="inline-flex items-center gap-1 text-sm font-bold text-ink" data-testid="verified">
            <ShieldCheck aria-hidden className="size-4" strokeWidth={2.25} />
            {t("verified")}
          </span>
        )}
      </div>
      {summary && summary.sentences.length > 0 ? (
        <ul className="mt-3 max-w-[68ch] list-disc space-y-2.5 ps-5 text-lg marker:text-ink-muted">
          <CitedText sentences={summary.sentences} lang={summary.lang} articles={articles} as="li" />
        </ul>
      ) : (
        <p className="mt-3 rounded-card bg-surface px-4 py-3 text-ink-muted">{t("unavailable")}</p>
      )}
    </section>
  );
}
