"use server";

import { getLocale } from "next-intl/server";

import { getFeed } from "@/lib/api/client";
import type { Page, StoryCard } from "@/lib/api/types";

/** Next feed page for infinite scroll. Runs on the server so it shares the page's data source. */
export async function loadFeedPage(cursor: string, topic?: string): Promise<Page<StoryCard>> {
  return getFeed({ cursor, topic, lang: await getLocale() });
}
