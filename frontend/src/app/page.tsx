import { getLocale, getTranslations } from "next-intl/server";

import { FeedLayout } from "@/components/story/FeedLayout";
import { getFeed } from "@/lib/api/client";
import { loadRail } from "@/lib/feed-data";

export default async function HomePage() {
  const locale = await getLocale();
  const t = await getTranslations("home");
  const [page, rail] = await Promise.all([getFeed({ tab: "home", lang: locale }), loadRail(locale)]);
  return (
    <FeedLayout
      heading={t("heading")}
      page={page}
      emptyMessage={t("empty")}
      blindspots={rail.blindspots}
      topicSlugs={rail.topics}
    />
  );
}
