import { Search } from "lucide-react";
import Link from "next/link";
import { getTranslations } from "next-intl/server";

import { LanguageSwitcher } from "./language-switcher";
import { primaryNav, topics } from "./nav-items";
import { TopicChips } from "./topic-chips";

export async function SiteHeader() {
  const t = await getTranslations("nav");
  const tt = await getTranslations("topics");
  const topicItems = topics.map((key) => ({ key, label: tt(key) }));
  return (
    <header className="sticky top-0 z-40 border-b bg-paper">
      <div className="mx-auto flex h-14 max-w-[1200px] items-center gap-6 px-4 md:px-6">
        <Link href="/" className="text-xl font-bold tracking-tight" lang="en">
          Lens
        </Link>
        <nav aria-label={t("primary")} className="hidden md:block">
          <ul className="flex items-center gap-4 whitespace-nowrap text-sm font-medium lg:gap-5">
            {primaryNav.map((item) => (
              <li key={item.key}>
                <Link href={item.href} className="text-ink-muted hover:text-ink">
                  {t(item.key)}
                </Link>
              </li>
            ))}
          </ul>
        </nav>
        <div className="ml-auto flex items-center gap-3">
          <Link
            href="/search"
            className="flex h-9 items-center gap-2 rounded-control bg-surface px-3 text-sm text-ink-muted lg:w-56"
          >
            <Search aria-hidden className="size-4" />
            <span className="sr-only lg:not-sr-only">{t("search")}</span>
          </Link>
          <LanguageSwitcher label={t("language")} />
          <Link href="/sign-in" className="hidden whitespace-nowrap text-sm font-medium lg:inline">
            {t("signIn")}
          </Link>
        </div>
      </div>
      <TopicChips label={t("topics")} items={topicItems} />
    </header>
  );
}
