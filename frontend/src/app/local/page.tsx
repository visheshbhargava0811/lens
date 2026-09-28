import { getTranslations } from "next-intl/server";

import { LocalFeed } from "@/components/local/LocalFeed";

export default async function LocalPage() {
  const t = await getTranslations("local");
  return (
    <div>
      <h1 className="text-3xl">{t("title")}</h1>
      <p className="mt-2 max-w-[60ch] text-ink-muted">{t("intro")}</p>
      <div className="mt-6">
        <LocalFeed />
      </div>
    </div>
  );
}
