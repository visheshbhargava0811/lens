"use client";

import { useLocale } from "next-intl";
import { useRouter } from "next/navigation";
import { useTransition } from "react";

import { setLocale } from "@/i18n/actions";
import type { Locale } from "@/i18n/config";
import { cn } from "@/lib/utils";

const options: { locale: Locale; label: string }[] = [
  { locale: "en", label: "EN" },
  { locale: "hi", label: "हिं" },
];

/** Changes UI and summary language only. Source headlines stay in their original script. */
export function LanguageSwitcher({ label }: { label: string }) {
  const current = useLocale();
  const router = useRouter();
  const [pending, startTransition] = useTransition();

  function select(locale: Locale) {
    startTransition(async () => {
      await setLocale(locale);
      router.refresh();
    });
  }

  return (
    <div role="group" aria-label={label} className="flex items-center rounded-control bg-surface p-0.5">
      {options.map((o) => (
        <button
          key={o.locale}
          type="button"
          lang={o.locale}
          aria-pressed={current === o.locale}
          disabled={pending}
          onClick={() => select(o.locale)}
          className={cn(
            "h-8 min-w-9 rounded-[6px] px-2 text-sm font-medium",
            current === o.locale ? "bg-paper text-ink shadow-sm" : "text-ink-muted hover:text-ink",
          )}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}
