import Link from "next/link";
import { getLocale, getTranslations } from "next-intl/server";

import { MethodologyLink } from "@/components/coverage/MethodologyLink";
import { EmptyState } from "@/components/states/EmptyState";
import { StoryCard } from "@/components/story/StoryCard";
import { getBlindspots } from "@/lib/api/client";
import { cn } from "@/lib/utils";

export default async function BlindspotPage({
  searchParams,
}: {
  searchParams: Promise<{ type?: string }>;
}) {
  const type = (await searchParams).type === "language" ? "language" : "stance";
  const locale = await getLocale();
  const t = await getTranslations("blindspot");
  const data = await getBlindspots(type, locale);

  const tabs = [
    { key: "stance", label: t("byStance"), href: "/blindspot" },
    { key: "language", label: t("byLanguage"), href: "/blindspot?type=language" },
  ] as const;

  return (
    <div className="space-y-6">
      <header className="max-w-[68ch]">
        <h1 className="text-3xl">{t("heading")}</h1>
        <p className="mt-2 text-ink-muted">{t("intro")}</p>
        <MethodologyLink href={data.methodology_url} className="mt-2 inline-block text-sm">
          {t("methodology")}
        </MethodologyLink>
      </header>

      <nav aria-label={t("tabs")}>
        <ul className="flex gap-1 border-b">
          {tabs.map((tab) => (
            <li key={tab.key}>
              <Link
                href={tab.href}
                aria-current={type === tab.key ? "page" : undefined}
                className={cn(
                  "-mb-px inline-flex h-10 items-center border-b-2 px-3 text-sm font-medium",
                  type === tab.key ? "border-ink text-ink" : "border-transparent text-ink-muted hover:text-ink",
                )}
              >
                {tab.label}
              </Link>
            </li>
          ))}
        </ul>
      </nav>

      {data.items.length === 0 ? (
        <EmptyState>{t("empty")}</EmptyState>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {data.items.map((s) => (
            <StoryCard key={s.id} story={s} strongBar />
          ))}
        </div>
      )}
    </div>
  );
}
