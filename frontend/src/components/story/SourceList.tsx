"use client";

import { useTranslations } from "next-intl";
import { useEffect, useMemo, useState } from "react";

import { MethodologyLink } from "@/components/coverage/MethodologyLink";
import type { ArticleRow as ArticleRowData } from "@/lib/api/types";
import { articleBucket, dominantTarget, type SegmentKey } from "@/lib/coverage";
import { languageName, sortedLanguages } from "@/lib/format";
import { cn } from "@/lib/utils";

import { ArticleRow, articleDomId } from "./ArticleRow";
import { SHOW_ARTICLE_EVENT } from "./events";

const STANCE_FILTERS: ("all" | SegmentKey)[] = ["all", "critical", "balanced", "supportive", "unclassified"];

export function SourceList({ articles, methodologyUrl }: { articles: ArticleRowData[]; methodologyUrl: string }) {
  const t = useTranslations();
  const [stance, setStance] = useState<"all" | SegmentKey>("all");
  const [lang, setLang] = useState<string>("all");
  const [highlighted, setHighlighted] = useState<string | null>(null);
  const target = useMemo(() => dominantTarget(articles), [articles]);

  const languages = useMemo(() => {
    const counts: Record<string, number> = {};
    for (const a of articles) counts[a.source.language] = (counts[a.source.language] ?? 0) + 1;
    return sortedLanguages(counts);
  }, [articles]);

  const stanceCounts = useMemo(() => {
    const counts: Record<string, number> = { all: articles.length };
    for (const a of articles) {
      const b = articleBucket(a.stance);
      counts[b] = (counts[b] ?? 0) + 1;
    }
    return counts;
  }, [articles]);

  const visible = articles.filter(
    (a) => (stance === "all" || articleBucket(a.stance) === stance) && (lang === "all" || a.source.language === lang),
  );

  // Citation chips reveal their article: clear filters, then scroll to and focus the row.
  useEffect(() => {
    function onShow(e: Event) {
      const id = (e as CustomEvent<string>).detail;
      setStance("all");
      setLang("all");
      setHighlighted(id);
      requestAnimationFrame(() => {
        const el = document.getElementById(articleDomId(id));
        const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
        el?.scrollIntoView({ behavior: reduce ? "auto" : "smooth", block: "center" });
        el?.focus({ preventScroll: true });
      });
    }
    window.addEventListener(SHOW_ARTICLE_EVENT, onShow);
    return () => window.removeEventListener(SHOW_ARTICLE_EVENT, onShow);
  }, []);

  const chip = (active: boolean) =>
    cn(
      "inline-flex h-8 shrink-0 items-center gap-1.5 rounded-chip px-3 text-sm font-medium",
      active ? "bg-ink text-paper" : "bg-surface text-ink hover:bg-line",
    );

  return (
    <section aria-labelledby="sources-heading" className="scroll-mt-32">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 id="sources-heading" className="text-2xl">
          {t("sources.title")}
        </h2>
        <MethodologyLink href={methodologyUrl}>{t("sources.howLabeled")}</MethodologyLink>
      </div>

      <div role="group" aria-label={t("sources.filterStance")} className="mt-3 flex gap-2 overflow-x-auto pb-1">
        {STANCE_FILTERS.map((key) => (
          <button
            key={key}
            type="button"
            aria-pressed={stance === key}
            onClick={() => setStance(key)}
            className={chip(stance === key)}
          >
            {key === "all" ? t("sources.all") : t(`stance.label.${key}`, { target })}
            <span className="tabular-nums opacity-70">{stanceCounts[key] ?? 0}</span>
          </button>
        ))}
      </div>
      <div role="group" aria-label={t("sources.filterLanguage")} className="mt-2 flex gap-2 overflow-x-auto pb-1">
        <button type="button" aria-pressed={lang === "all"} onClick={() => setLang("all")} className={chip(lang === "all")}>
          {t("sources.all")}
        </button>
        {languages.map(([code, count]) => (
          <button
            key={code}
            type="button"
            aria-pressed={lang === code}
            onClick={() => setLang(code)}
            className={chip(lang === code)}
          >
            <span lang={code}>{languageName(code, code)}</span>
            <span className="tabular-nums opacity-70">{count}</span>
          </button>
        ))}
      </div>

      <p className="mt-3 text-sm text-ink-muted" aria-live="polite">
        {t("sources.count", { count: visible.length })}
      </p>
      {visible.length === 0 ? (
        <p className="mt-2 rounded-control bg-surface px-3 py-4 text-sm">{t("sources.empty")}</p>
      ) : (
        <ul className="mt-1">
          {visible.map((a) => (
            <ArticleRow key={a.id} article={a} highlighted={a.id === highlighted} />
          ))}
        </ul>
      )}
    </section>
  );
}
