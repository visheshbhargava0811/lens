"use client";

import { ShieldCheck } from "lucide-react";
import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";

import { CoverageBar } from "@/components/coverage/CoverageBar";
import { biasFill } from "@/components/coverage/bias-style";
import type { CitedArticle } from "@/components/story/CitationChip";
import { SHOW_ARTICLE_EVENT } from "@/components/story/events";
import { FactCheckList } from "@/components/story/FactCheckList";
import { CitedText } from "@/components/story/SummaryBlock";
import type { AskAnswer, AskEvidence, CitedSentence } from "@/lib/api/types";
import { cn } from "@/lib/utils";
import { safeUrl } from "@/lib/safe-url";

export function askArticleDomId(id: string) {
  return `ask-article-${id}`;
}

/**
 * docs/10 Ask answer card: cited sentences, coverage from data (not the model), agreements and
 * differences, premises, limitations, sources used, and up to three follow-ups.
 */
export function AnswerCard({
  answer,
  evidence,
  onFollowUp,
}: {
  answer: AskAnswer;
  evidence: AskEvidence | null;
  onFollowUp: (q: string) => void;
}) {
  const t = useTranslations();
  const [highlighted, setHighlighted] = useState<string | null>(null);
  const articles: Record<string, CitedArticle> = Object.fromEntries(
    answer.articles.map((a) => [
      a.id,
      {
        id: a.id,
        headline: a.headline,
        headline_lang: a.headline_lang,
        url: a.url,
        sourceName: a.source_name,
        sourceLanguage: a.source_language,
      },
    ]),
  );

  useEffect(() => {
    function onShow(e: Event) {
      const id = (e as CustomEvent<string>).detail;
      setHighlighted(id);
      requestAnimationFrame(() => {
        const el = document.getElementById(askArticleDomId(id));
        const reduce = window.matchMedia(
          "(prefers-reduced-motion: reduce)",
        ).matches;
        el?.scrollIntoView({
          behavior: reduce ? "auto" : "smooth",
          block: "center",
        });
        el?.focus({ preventScroll: true });
      });
    }
    window.addEventListener(SHOW_ARTICLE_EVENT, onShow);
    return () => window.removeEventListener(SHOW_ARTICLE_EVENT, onShow);
  }, []);

  const section = (id: string, title: string, sentences: CitedSentence[]) =>
    sentences.length > 0 && (
      <section aria-labelledby={id}>
        <h3 id={id} className="text-lg">
          {title}
        </h3>
        <ul className="mt-2 list-disc space-y-2 ps-5 marker:text-ink-muted">
          <CitedText
            sentences={sentences}
            lang={answer.lang}
            articles={articles}
            as="li"
          />
        </ul>
      </section>
    );
  const biasOf = Object.fromEntries(
    (evidence?.sources ?? []).map((s) => [s.name, s.bias]),
  );
  const sourceCount = new Set(answer.articles.map((a) => a.source_name)).size;

  return (
    <article
      data-testid="answer-card"
      aria-labelledby="answer-heading"
      className="flex flex-col gap-6"
    >
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
        <h2 id="answer-heading" className="text-2xl">
          {t("ask.answer")}
        </h2>
        <span
          className="inline-flex items-center gap-1 text-sm font-bold text-ink"
          data-testid="verified"
        >
          <ShieldCheck aria-hidden className="size-4" strokeWidth={2.25} />
          {t("summary.verified")}
        </span>
        {answer.lang !== "en" && (
          // Answers are written and verified in English, then translated and checked (G-OUT-06).
          <span
            className="rounded-chip bg-surface px-2 py-0.5 text-xs font-bold text-ink-muted"
            data-testid="translated"
          >
            {t("summary.translated", { language: t("languageNames.en") })}
          </span>
        )}
      </div>
      {answer.basis === "stored_summary" && (
        <p
          className="rounded-card bg-flag-bg px-4 py-3 text-sm text-flag-ink"
          data-testid="stored-summary-note"
        >
          {t("ask.storedSummary")}
        </p>
      )}
      <div className="max-w-[68ch] space-y-2 text-lg" data-testid="answer-tldr">
        <CitedText
          sentences={answer.tldr}
          lang={answer.lang}
          articles={articles}
        />
      </div>

      <section
        aria-labelledby="answer-coverage"
        className="rounded-card bg-surface p-4"
      >
        <h3 id="answer-coverage" className="text-base">
          {t("ask.coverage")}
        </h3>
        <CoverageBar
          coverage={answer.coverage}
          sourceCount={sourceCount}
          size="md"
          className="mt-2"
        />
      </section>

      {section("answer-what", t("ask.whatHappened"), answer.what_happened)}
      {section("answer-agree", t("summary.agreements"), answer.agreements)}
      {section(
        "answer-differ",
        t("summary.disagreements"),
        answer.disagreements,
      )}
      {section("answer-premises", t("ask.premises"), answer.premises_addressed)}

      {answer.fact_checks.length > 0 && (
        <section aria-labelledby="answer-factchecks" data-testid="fact-checks">
          <h3 id="answer-factchecks" className="text-lg font-bold">
            {t("story.factChecks")}
          </h3>
          <FactCheckList
            items={answer.fact_checks}
            panel="rounded-card bg-card p-4"
          />
        </section>
      )}
      {answer.limitations.length > 0 && (
        <section aria-labelledby="answer-limits">
          <h3 id="answer-limits" className="text-lg">
            {t("ask.limitations")}
          </h3>
          <ul
            lang={answer.lang}
            className="mt-2 list-disc space-y-1 ps-5 text-ink-muted marker:text-ink-muted"
            data-testid="limitations"
          >
            {answer.limitations.map((l) => (
              <li key={l}>{l}</li>
            ))}
          </ul>
        </section>
      )}

      {answer.articles.length > 0 && (
        <section aria-labelledby="answer-sources">
          <h3 id="answer-sources" className="text-lg">
            {t("ask.sourcesUsed")}
          </h3>
          <ul className="mt-2 divide-y divide-ink/10">
            {answer.articles.map((a) => {
              const bias = biasOf[a.source_name] ?? "unrated";
              return (
                <li
                  key={a.id}
                  id={askArticleDomId(a.id)}
                  tabIndex={-1}
                  className={cn(
                    "flex flex-col gap-1 py-3 outline-none",
                    highlighted === a.id && "bg-surface",
                  )}
                >
                  <span className="flex flex-wrap items-center gap-2 text-sm text-ink-muted">
                    <span className="font-bold text-ink">{a.source_name}</span>
                    <span>{a.source_language}</span>
                    <span className="inline-flex items-center gap-1">
                      <span
                        aria-hidden
                        className={cn(
                          "inline-block size-2.5 rounded-[2px]",
                          biasFill[bias],
                        )}
                      />
                      {t(`bias.label.${bias}`)}
                    </span>
                  </span>
                  <a
                    href={safeUrl(a.url)}
                    target="_blank"
                    rel="noopener noreferrer"
                    lang={a.headline_lang}
                    className="font-medium underline decoration-ink/30 hover:decoration-ink"
                  >
                    {a.headline}
                    <span className="sr-only"> {t("sources.newTab")}</span>
                  </a>
                </li>
              );
            })}
          </ul>
        </section>
      )}

      {answer.follow_up_questions.length > 0 && (
        <section aria-labelledby="answer-follow">
          <h3 id="answer-follow" className="text-lg">
            {t("ask.followUps")}
          </h3>
          <div className="mt-2 flex flex-wrap gap-2" lang={answer.lang}>
            {answer.follow_up_questions.slice(0, 3).map((q) => (
              <button
                key={q}
                type="button"
                onClick={() => onFollowUp(q)}
                className="rounded-chip bg-surface px-3 py-1.5 text-left text-sm font-medium hover:bg-line"
              >
                {q}
              </button>
            ))}
          </div>
        </section>
      )}
    </article>
  );
}
