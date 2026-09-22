import { Search } from "lucide-react";
import Link from "next/link";
import { getLocale, getNow, getTranslations } from "next-intl/server";

import { LanguageSwitcher } from "./language-switcher";
import { NavLinks } from "./nav-links";
import { primaryNav, topics } from "./nav-items";
import { TopicChips } from "./topic-chips";

export async function SiteHeader() {
  const t = await getTranslations("nav");
  const tt = await getTranslations("topics");
  const locale = await getLocale();
  const now = await getNow();
  const today = new Intl.DateTimeFormat(locale === "hi" ? "hi-IN" : "en-IN", {
    weekday: "long",
    day: "numeric",
    month: "long",
    year: "numeric",
    timeZone: "Asia/Kolkata",
  }).format(now);
  const topicItems = topics.map((key) => ({ key, label: tt(key) }));
  const navItems = primaryNav.map((item) => ({ href: item.href, label: t(item.key) }));

  return (
    <>
      <div role="region" aria-label={t("language")} className="bg-strip text-strip-ink">
        <div className="mx-auto flex h-10 max-w-[1280px] items-center justify-between gap-4 px-4 text-xs md:px-6">
          <p>
            <span className="sr-only">{t("today")}: </span>
            <time dateTime={now.toISOString().slice(0, 10)}>{today}</time>
          </p>
          <LanguageSwitcher label={t("language")} />
        </div>
      </div>
      <header className="sticky top-0 z-40 border-b bg-paper">
        <div className="mx-auto flex h-16 max-w-[1280px] items-center gap-8 px-4 md:px-6">
          <Link href="/" lang="en" className="text-[1.75rem] leading-none font-extrabold tracking-[-0.04em]">
            Lens
          </Link>
          <NavLinks label={t("primary")} items={navItems} />
          <div className="ms-auto flex items-center gap-2">
            <Link
              href="/search"
              className="flex h-10 items-center gap-2.5 rounded-control border border-ink/25 bg-card px-3 text-sm text-ink-muted hover:border-ink/60 lg:w-64"
            >
              <Search aria-hidden className="size-4 text-ink" />
              <span className="sr-only lg:not-sr-only">{t("search")}</span>
            </Link>
            <Link
              href="/sign-in"
              className="hidden h-10 items-center rounded-control bg-ink px-5 text-sm font-bold whitespace-nowrap text-paper hover:bg-ink/85 md:inline-flex"
            >
              {t("signIn")}
            </Link>
          </div>
        </div>
        <TopicChips label={t("topics")} items={topicItems} />
      </header>
    </>
  );
}
