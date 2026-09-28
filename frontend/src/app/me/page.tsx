import { getTranslations } from "next-intl/server";

import { MemoryPanel } from "@/components/me/MemoryPanel";

export default async function MePage() {
  const t = await getTranslations("me");
  return (
    <div className="mx-auto max-w-3xl">
      <h1 className="text-3xl">{t("title")}</h1>
      <p className="mt-2 mb-6 text-ink-muted">{t("intro")}</p>
      <MemoryPanel />
    </div>
  );
}
