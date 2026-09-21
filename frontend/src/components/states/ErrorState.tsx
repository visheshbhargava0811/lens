"use client";

import { useTranslations } from "next-intl";

/** Says what happened and what to do. Never apologizes, never vague. */
export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  const t = useTranslations("errors");
  return (
    <div role="alert" data-testid="error-state" className="rounded-card border px-4 py-6">
      <p>{message}</p>
      {onRetry && (
        <button
          type="button"
          onClick={onRetry}
          className="mt-3 h-9 rounded-control bg-ink px-4 text-sm font-medium text-paper hover:bg-ink/90"
        >
          {t("tryAgain")}
        </button>
      )}
    </div>
  );
}
