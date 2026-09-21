import Link from "next/link";
import { getTranslations } from "next-intl/server";

export default async function StoryNotFound() {
  const t = await getTranslations();
  return (
    <div className="py-12">
      <h1 className="text-2xl">{t("story.notFound")}</h1>
      <Link href="/" className="mt-4 inline-block font-medium text-link hover:underline">
        {t("errors.goHome")}
      </Link>
    </div>
  );
}
