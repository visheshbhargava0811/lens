import { useFormatter, useLocale, useNow, useTranslations } from "next-intl";

import type { StoryCard } from "@/lib/api/types";
import { languageName, sortedLanguages } from "@/lib/format";

/** Source count, updated time, language mix. Separate labeled elements, not a dotted string. */
export function StoryMeta({ story, maxLanguages = 3 }: { story: StoryCard; maxLanguages?: number }) {
  const t = useTranslations();
  const format = useFormatter();
  const now = useNow();
  const locale = useLocale();
  const langs = sortedLanguages(story.counts.by_language);
  const shown = langs.slice(0, maxLanguages);
  const rest = langs.length - shown.length;
  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-ink-muted">
      <span className="font-medium text-ink">{t("coverage.sources", { count: story.counts.sources })}</span>
      <time dateTime={story.updated_at}>
        {t("story.updated", { time: format.relativeTime(new Date(story.updated_at), now) })}
      </time>
      {maxLanguages > 0 && (
        <span className="flex flex-wrap gap-x-2">
          <span className="sr-only">{t("story.languages")}</span>
          {shown.map(([code, count]) => (
            <span key={code}>{t("story.languageCount", { language: languageName(code, locale), count })}</span>
          ))}
          {rest > 0 && <span>+{rest}</span>}
        </span>
      )}
    </div>
  );
}
