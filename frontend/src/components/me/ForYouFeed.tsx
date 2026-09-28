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
        if (!me.signed_in_with) return { kind: "off" }; // For you needs sign-in (ADR-0044)
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
  if (view.kind === "off")
    return (
      <div className="rounded-card bg-surface p-5">
        <p>{t("forYouOff")}</p>
        <Link
          href="/sign-in?next=/for-you"
          className="mt-4 inline-flex h-10 items-center rounded-control bg-ink px-5 text-sm font-bold text-paper hover:bg-ink/85"
        >
          {t("forYouSignIn")}
        </Link>
      </div>
    );
  if (view.kind === "noTopics")
    return (
      <p className="rounded-card bg-surface p-5">
        {t("forYouNoTopics")}{" "}
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
