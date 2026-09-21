"use client";

import { useTranslations } from "next-intl";

import { ErrorState } from "@/components/states/ErrorState";

export default function FeedError({ reset }: { error: Error; reset: () => void }) {
  const t = useTranslations("errors");
  return <ErrorState message={t("feed")} onRetry={reset} />;
}
