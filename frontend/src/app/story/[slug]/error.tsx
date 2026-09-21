"use client";

import { useTranslations } from "next-intl";

import { ErrorState } from "@/components/states/ErrorState";

export default function StoryError({ reset }: { error: Error; reset: () => void }) {
  const t = useTranslations("story");
  return <ErrorState message={t("loadError")} onRetry={reset} />;
}
