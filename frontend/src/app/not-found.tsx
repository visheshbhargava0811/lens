import Link from "next/link";
import { getTranslations } from "next-intl/server";

export default async function NotFound() {
  const t = await getTranslations("errors");
  return (
    <div className="py-16">
      <h1 className="max-w-[24ch] text-4xl">{t("notFound")}</h1>
      <Link href="/" className="mt-6 inline-flex h-11 items-center rounded-control bg-ink px-6 font-bold text-paper hover:bg-ink/85">
        {t("goHome")}
      </Link>
    </div>
  );
}
