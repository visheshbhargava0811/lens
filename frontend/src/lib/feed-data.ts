import { getBlindspots, getTopics } from "@/lib/api/client";
import type { StoryCard, Topic } from "@/lib/api/types";

/** Rail data is secondary: a failure here must not break the feed. */
export async function loadRail(lang: string): Promise<{ blindspots: StoryCard[]; topics: Topic[] }> {
  const [stance, language, topics] = await Promise.allSettled([
    getBlindspots("bias", lang),
    getBlindspots("language", lang),
    getTopics(lang),
  ]);
  const blindspots = [stance, language].flatMap((r) => (r.status === "fulfilled" ? r.value.items : []));
  return {
    blindspots,
    topics: topics.status === "fulfilled" ? topics.value.items.filter((t) => t.slug !== "top") : [],
  };
}
