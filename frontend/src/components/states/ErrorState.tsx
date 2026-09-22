"use client";

import { useTranslations } from "next-intl";

/** Says what happened and what to do. Never apologizes, never vague. */
export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  const t = useTranslations("errors");
  return (
    <div role="alert" data-testid="error-state" className="rounded-card bg-surface px-5 py-6">
      <p>{message}</p>
      {onRetry && (
        <button
          type="button"
          onClick={onRetry}
          className="mt-4 h-10 rounded-control bg-ink px-5 text-sm font-bold text-paper hover:bg-ink/85"
        >
          {t("tryAgain")}
        </button>
      )}
    </div>
  );
}
