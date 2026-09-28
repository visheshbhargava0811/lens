"use client";

import { ArrowRight, LoaderCircle, Square } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import { useEffect, useRef, useState } from "react";

import { ErrorState } from "@/components/states/ErrorState";
import { StoryCard } from "@/components/story/StoryCard";
import { ApiRequestError, askStream, type AskEvent } from "@/lib/api/client";
import type {
  AskAbstain,
  AskAnswer,
  AskEvidence,
  AskStatus,
  AskUnderstanding,
} from "@/lib/api/types";

import { AnswerCard } from "./AnswerCard";

type Run = {
  status: AskStatus["step"] | null;
  understanding: AskUnderstanding | null;
  evidence: AskEvidence | null;
  answer: AskAnswer | null;
  abstain: AskAbstain | null;
  error: string | null;
};
const EMPTY: Run = {
  status: null,
  understanding: null,
  evidence: null,
  answer: null,
  abstain: null,
  error: null,
};

function reduce(r: Run, e: AskEvent, errorMessage: string): Run {
  switch (e.event) {
    case "status":
      return { ...r, status: e.data.step };
    case "understanding":
      return { ...r, understanding: e.data };
    case "evidence":
      return { ...r, evidence: e.data };
    case "answer_final":
      return { ...r, answer: e.data, status: null };
    case "abstain":
      return { ...r, abstain: e.data, status: null };
    case "error":
      return { ...r, error: errorMessage, status: null };
  }
}

/** docs/10 Ask: one input, a single updating status line, then one verified answer or an abstain. */
export function AskPanel({ initialQuery = "" }: { initialQuery?: string }) {
  const t = useTranslations();
  const locale = useLocale();
  const [query, setQuery] = useState(initialQuery);
  const [neutral, setNeutral] = useState("");
  const [run, setRun] = useState<Run>(EMPTY);
  const [running, setRunning] = useState(false);
  const abort = useRef<AbortController | null>(null);
  // One conversation per page visit: follow-ups see the earlier questions, never earlier answers (docs/11).
  const sessionId = useRef<string>(crypto.randomUUID());
  const started = useRef(false);

  async function ask(q: string) {
    const text = q.trim();
    if (!text || running) return;
    setQuery(text);
    abort.current = new AbortController();
    setRunning(true);
    setRun({ ...EMPTY, status: "understanding" });
    const apply = (e: AskEvent) => {
      if (e.event === "understanding") setNeutral(e.data.neutral_query);
      setRun((r) => reduce(r, e, t("ask.error")));
    };
    try {
      await askStream(
        { query: text, lang: locale, session_id: sessionId.current },
        apply,
        abort.current.signal,
      );
    } catch (e) {
      if (e instanceof DOMException && e.name === "AbortError") {
        setRun((r) => ({ ...r, status: null }));
      } else if (e instanceof ApiRequestError && e.status === 429) {
        setRun({
          ...EMPTY,
          error: t("ask.rateLimited", { seconds: e.retryAfterS ?? 10 }),
        });
      } else {
        setRun({ ...EMPTY, error: t("ask.error") });
      }
    } finally {
      setRunning(false);
      abort.current = null;
    }
  }

  useEffect(() => {
    if (initialQuery && !started.current) {
      started.current = true;
      void ask(initialQuery);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- run once for a ?q= link
  }, []);

  const u = run.understanding;
  const showNeutral =
    u && u.removed_premises.length > 0 && (run.answer || run.abstain);

  return (
    <div className="flex flex-col gap-6">
      <form
        role="search"
        onSubmit={(e) => {
          e.preventDefault();
          void ask(query);
        }}
        className="flex items-stretch gap-2"
      >
        <label htmlFor="ask-input" className="sr-only">
          {t("ask.label")}
        </label>
        <input
          id="ask-input"
          data-testid="ask-input"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder={t("ask.placeholder")}
          maxLength={500}
          disabled={running}
          autoComplete="off"
          className="h-12 min-w-0 flex-1 rounded-control border-2 border-ink bg-paper px-4 text-base placeholder:text-ink-muted disabled:opacity-60"
        />
        {running ? (
          <button
            type="button"
            onClick={() => abort.current?.abort()}
            className="inline-flex h-12 items-center gap-2 rounded-control bg-surface px-4 font-bold hover:bg-line"
          >
            <Square aria-hidden className="size-4" />
            {t("ask.stop")}
          </button>
        ) : (
          <button
            type="submit"
            data-testid="ask-submit"
            className="inline-flex h-12 items-center gap-2 rounded-control bg-ink px-5 font-bold text-paper hover:bg-ink/85"
          >
            {t("ask.submit")}
            <ArrowRight aria-hidden className="size-4" />
          </button>
        )}
      </form>

      <p
        aria-live="polite"
        data-testid="ask-status"
        className="min-h-6 text-ink-muted"
      >
        {run.status && (
          <span className="inline-flex items-center gap-2">
            <LoaderCircle
              aria-hidden
              className="size-4 animate-spin motion-reduce:animate-none"
            />
            {t(`ask.status.${run.status}`)}
          </span>
        )}
      </p>

      {showNeutral && (
        <form
          data-testid="neutral-note"
          onSubmit={(e) => {
            e.preventDefault();
            void ask(neutral);
          }}
          className="rounded-card bg-surface p-4 text-sm"
        >
          <label htmlFor="neutral-input" className="block text-ink-muted">
            {t("ask.neutralNote")}
          </label>
          <div className="mt-2 flex flex-wrap gap-2">
            <input
              id="neutral-input"
              value={neutral}
              onChange={(e) => setNeutral(e.target.value)}
              className="h-10 min-w-0 flex-1 rounded-control border border-ink/30 bg-paper px-3"
            />
            <button
              type="submit"
              className="h-10 rounded-control bg-ink px-4 font-bold text-paper hover:bg-ink/85"
            >
              {t("ask.editQuery")}
            </button>
          </div>
        </form>
      )}

      {run.error && (
        <ErrorState message={run.error} onRetry={() => void ask(query)} />
      )}

      {run.answer && (
        <AnswerCard
          answer={run.answer}
          evidence={run.evidence}
          onFollowUp={(q) => void ask(q)}
        />
      )}

      {run.abstain && (
        <section
          data-testid="abstain-state"
          aria-labelledby="abstain-heading"
          className="flex flex-col gap-4"
        >
          <p
            id="abstain-heading"
            className="rounded-card bg-surface px-5 py-4 text-lg"
          >
            {t(`ask.abstain.${run.abstain.reason}`)}
          </p>
          {run.abstain.closest_stories.length > 0 && (
            <>
              <h2 className="text-xl">{t("ask.closest")}</h2>
              <div className="grid gap-6 md:grid-cols-2">
                {run.abstain.closest_stories.map((s) => (
                  <StoryCard key={s.id} story={s} />
                ))}
              </div>
            </>
          )}
        </section>
      )}
    </div>
  );
}
