import { EyeOff } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";

import type { Blindspot } from "@/lib/api/types";
import { languageName } from "@/lib/format";
import { cn } from "@/lib/utils";

/** Plain-language blindspot note in flag colors. Neutral: no group is implied to be wrong. */
export function FlagChip({ blindspot, className }: { blindspot: Blindspot; className?: string }) {
  const t = useTranslations();
  const locale = useLocale();
  let text: string;
  if (blindspot.type === "stance") {
    text = t("flag.stance", { phrase: t(`stance.phrase.${blindspot.skew}`) });
  } else {
    // skew is a language group from the backend: "en" or "indic" (ADR-0018); older data may hold a code.
    const language = blindspot.skew === "indic" ? t("flag.indianLanguages") : languageName(blindspot.skew, locale);
    const other = blindspot.skew === "en" ? t("flag.otherThanEnglish") : languageName("en", locale);
    text = t("flag.language", { language, other });
  }
  return (
    <p
      className={cn(
        "relative z-10 inline-flex items-center gap-1.5 rounded-chip bg-flag-bg px-2 py-0.5 text-xs font-bold text-flag-ink",
        className,
      )}
      data-testid="flag-chip"
    >
      <EyeOff aria-hidden className="size-3.5 shrink-0" strokeWidth={2.25} />
      {text}
    </p>
  );
}
