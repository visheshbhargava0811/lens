import { House, MessageCircleQuestion, EyeOff, MapPin, User } from "lucide-react";
import Link from "next/link";
import { getTranslations } from "next-intl/server";

import { mobileTabs } from "./nav-items";

const icons = { home: House, blindspot: EyeOff, ask: MessageCircleQuestion, local: MapPin, profile: User };

export async function BottomTabBar() {
  const t = await getTranslations("nav");
  return (
    <nav aria-label={t("primary")} className="fixed inset-x-0 bottom-0 z-40 border-t border-ink/20 bg-paper md:hidden">
      <ul className="grid grid-cols-5 pb-[env(safe-area-inset-bottom)]">
        {mobileTabs.map((tab) => {
          const Icon = icons[tab.key];
          return (
            <li key={tab.key}>
              <Link
                href={tab.href}
                className="flex h-14 flex-col items-center justify-center gap-0.5 text-[0.6875rem] font-bold text-ink"
              >
                <Icon aria-hidden className="size-5" strokeWidth={2.25} />
                {t(tab.key)}
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
