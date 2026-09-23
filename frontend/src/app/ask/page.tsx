import { getTranslations } from "next-intl/server";

import { AskPanel } from "@/components/ask/AskPanel";

export default async function AskPage({ searchParams }: { searchParams: Promise<{ q?: string | string[] }> }) {
  const { q } = await searchParams;
  const t = await getTranslations("ask");
  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-6 py-8 md:py-12">
      <div>
        <h1 className="text-4xl md:text-5xl">{t("title")}</h1>
        <p className="mt-3 max-w-[60ch] text-lg text-ink-muted">{t("intro")}</p>
      </div>
      <AskPanel initialQuery={typeof q === "string" ? q : ""} />
    </div>
  );
}
