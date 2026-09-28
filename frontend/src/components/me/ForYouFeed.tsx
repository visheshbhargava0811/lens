"use client";

import { useTranslations } from "next-intl";
import Link from "next/link";
import { useEffect, useState } from "react";

import { FeedGrid } from "@/components/story/FeedLayout";
import { getForYou, getMe } from "@/lib/api/client";
import type { Page, StoryCard } from "@/lib/api/types";

type View =
  | { kind: "loading" }
  | { kind: "off" }
  | { kind: "noTopics" }
  | { kind: "feed"; page: Page<StoryCard> };

/** For you (docs/11): stories in followed topics. Selection and order only; every story shows all its outlets. */
export function ForYouFeed() {
  const t = useTranslations("me");
  const [view, setView] = useState<View>({ kind: "loading" });

  useEffect(() => {
    getMe()
      .then(async (me): Promise<View> => {
        if (!me.consented) return { kind: "off" };
        const topics = me.preferences.followed_topics;
        if (!Array.isArray(topics) || topics.length === 0)
          return { kind: "noTopics" };
        return { kind: "feed", page: await getForYou() };
      })
      .then(setView)
      .catch(() => setView({ kind: "off" }));
  }, []);

  if (view.kind === "loading")
    return (
      <p aria-busy="true" className="text-ink-muted">
        …
      </p>
    );
  if (view.kind !== "feed")
    return (
      <p className="rounded-card bg-surface p-5">
        {t(view.kind === "off" ? "forYouOff" : "forYouNoTopics")}{" "}
        <Link href="/me" className="font-bold underline">
          {t("setUp")}
        </Link>
      </p>
    );
  return (
    <>
      <p className="mb-2 text-sm text-ink-muted">{t("forYouNote")}</p>
      <FeedGrid stories={view.page.items} />
    </>
  );
}
