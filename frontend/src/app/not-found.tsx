import Link from "next/link";
import { getTranslations } from "next-intl/server";

export default async function NotFound() {
  const t = await getTranslations("errors");
  return (
    <div className="py-12">
      <h1 className="text-2xl">{t("notFound")}</h1>
      <Link href="/" className="mt-4 inline-block font-medium text-link hover:underline">
        {t("goHome")}
      </Link>
    </div>
  );
}
