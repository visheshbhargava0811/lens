import { getLocale, getTranslations } from "next-intl/server";

import { FeedLayout } from "@/components/story/FeedLayout";
import { getFeed } from "@/lib/api/client";
import { loadRail } from "@/lib/feed-data";

export default async function TopicPage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  const locale = await getLocale();
  const t = await getTranslations();
  const [page, rail] = await Promise.all([getFeed({ topic: slug, lang: locale }), loadRail(locale)]);
  const name = rail.topics.find((tp) => tp.slug === slug)?.name ?? slug;
  return (
    <FeedLayout
      heading={t("topic.heading", { topic: name })}
      page={page}
      emptyMessage={t("topic.empty", { topic: name })}
      blindspots={rail.blindspots}
      topicSlugs={rail.topics}
      topic={slug}
    />
  );
}
