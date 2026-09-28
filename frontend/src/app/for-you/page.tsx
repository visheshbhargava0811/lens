import { getTranslations } from "next-intl/server";

import { ForYouFeed } from "@/components/me/ForYouFeed";

export default async function ForYouPage() {
  const t = await getTranslations("me");
  return (
    <div>
      <h1 className="text-3xl">{t("forYouTitle")}</h1>
      <div className="mt-4">
        <ForYouFeed />
      </div>
    </div>
  );
}
