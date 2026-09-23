import { EyeOff } from "lucide-react";
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
  const type = (await searchParams).type === "language" ? "language" : "bias";
  const locale = await getLocale();
  const t = await getTranslations("blindspot");
  const data = await getBlindspots(type, locale);

  const tabs = [
    { key: "bias", label: t("byBias"), href: "/blindspot" },
    { key: "language", label: t("byLanguage"), href: "/blindspot?type=language" },
  ] as const;

  return (
    <div className="space-y-8">
      <header className="flex flex-col gap-4 border-b border-ink/15 pb-8 md:flex-row md:items-center md:gap-8">
        <h1 className="flex shrink-0 items-center gap-3 text-4xl md:text-5xl">
          <EyeOff aria-hidden className="size-10 md:size-12" strokeWidth={2.5} />
          {t("heading")}
        </h1>
        <div className="max-w-[56ch] md:border-s md:border-ink/20 md:ps-8">
          <p className="text-lg">{t("intro")}</p>
          <MethodologyLink href={data.methodology_url} className="mt-2 inline-block text-sm">
            {t("methodology")}
          </MethodologyLink>
        </div>
      </header>

      <nav aria-label={t("tabs")}>
        <ul className="inline-flex gap-1 rounded-control bg-surface p-1">
          {tabs.map((tab) => (
            <li key={tab.key}>
              <Link
                href={tab.href}
                aria-current={type === tab.key ? "page" : undefined}
                className={cn(
                  "inline-flex h-9 items-center rounded-[2px] px-4 text-sm font-bold",
                  type === tab.key ? "bg-card text-ink" : "text-ink-muted hover:text-ink",
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
        <div className="grid gap-x-10 sm:grid-cols-2 lg:grid-cols-3">
          {data.items.map((s) => (
            <div key={s.id} className="border-t border-ink/15 py-6">
              <StoryCard story={s} strongBar />
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
