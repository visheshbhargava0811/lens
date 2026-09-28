"use client";

import { useFormatter, useTranslations } from "next-intl";
import { useEffect, useState } from "react";

import { FactCheckList } from "@/components/story/FactCheckList";
import { recordView } from "@/lib/api/client";
import type { StoryChanges } from "@/lib/api/types";

/**
 * docs/11 episodic memory: "What changed since you last looked". Records the view for consented readers and
 * shows only articles and fact-checks published after their previous visit (built by code, each item cited).
 * Readers without consent see nothing: the call is refused and no view is stored.
 */
export function WhatChanged({ storyId }: { storyId: string }) {
  const t = useTranslations("me");
  const fmt = useFormatter();
  const [changes, setChanges] = useState<StoryChanges | null>(null);

  useEffect(() => {
    recordView(storyId)
      .then(setChanges)
      .catch(() => setChanges(null));
  }, [storyId]);

  if (!changes) return null;
  const empty =
    changes.new_articles.length === 0 &&
    changes.new_fact_checks.length === 0 &&
    !changes.summary_updated;
  return (
    <section
      aria-labelledby="changes-heading"
      className="rounded-card bg-surface p-5"
      data-testid="what-changed"
    >
      <h2 id="changes-heading" className="text-xl">
        {t("changesTitle")}
      </h2>
      <p className="text-sm text-ink-muted">
        {t("changesSince", {
          date: fmt.dateTime(new Date(changes.since), {
            dateStyle: "medium",
            timeStyle: "short",
          }),
        })}
      </p>
      {empty && <p className="mt-2">{t("changesNone")}</p>}
      {changes.summary_updated && (
        <p className="mt-2 font-bold">{t("changesSummary")}</p>
      )}
      {changes.new_articles.length > 0 && (
        <>
          <h3 className="mt-3 text-base">{t("changesArticles")}</h3>
          <ul className="mt-1 space-y-1">
            {changes.new_articles.map((a) => (
              <li key={a.id} className="text-sm">
                <b>{a.source_name}</b>:{" "}
                <a
                  href={a.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  lang={a.headline_lang}
                  className="underline"
                >
                  {a.headline}
                </a>
              </li>
            ))}
          </ul>
        </>
      )}
      {changes.new_fact_checks.length > 0 && (
        <>
          <h3 className="mt-3 text-base">{t("changesFactChecks")}</h3>
          <FactCheckList
            items={changes.new_fact_checks}
            panel="rounded-card bg-card p-4"
          />
        </>
      )}
    </section>
  );
}
