import Link from "next/link";
import { getTranslations } from "next-intl/server";

type NavKey = "forYou" | "local" | "ask" | "search" | "signIn" | "profile";

/** Placeholder for routes planned in later phases (docs/12), so nav links never 404. */
export async function ComingSoon({ page }: { page: NavKey }) {
  const t = await getTranslations();
  return (
    <div className="py-16">
      <h1 className="text-4xl md:text-5xl">{t(`nav.${page}`)}</h1>
      <p className="mt-4 inline-block rounded-chip bg-flag-bg px-2 py-0.5 text-sm font-bold text-flag-ink">
        {t("states.comingSoon")}
      </p>
      <p className="mt-4 max-w-[52ch] text-lg text-ink-muted">{t("states.comingSoonBody")}</p>
      <Link
        href="/"
        className="mt-8 inline-flex h-11 items-center rounded-control bg-ink px-6 font-bold text-paper hover:bg-ink/85"
      >
        {t("errors.goHome")}
      </Link>
    </div>
  );
}
