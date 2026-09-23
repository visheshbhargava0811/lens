import { useTranslations } from "next-intl";

import type { Coverage } from "@/lib/api/types";
import { segmentsFromCoverage } from "@/lib/coverage";
import { cn } from "@/lib/utils";

import { biasFill } from "./bias-style";

/** Swatch plus pattern plus label plus count and share. */
export function BiasLegend({
  coverage,
  compact = false,
}: {
  coverage: Coverage;
  compact?: boolean;
}) {
  const t = useTranslations();
  if (!coverage.available) return null;
  const segments = segmentsFromCoverage(coverage);
  return (
    <ul
      aria-label={t("coverage.legend")}
      className={cn("text-sm", compact ? "flex flex-wrap gap-x-4 gap-y-1" : "space-y-1.5")}
    >
      {segments.map((s) => (
        <li key={s.key} className="flex items-center gap-2">
          <span aria-hidden className={cn("size-3.5 shrink-0 rounded-[1px] ring-1 ring-ink/20", biasFill[s.key])} />
          <span className={compact ? "" : "flex-1"}>{t(`bias.label.${s.key}`)}</span>
          <span className="tabular-nums text-ink-muted">
            {compact ? `${s.pct}%` : `${t("coverage.sources", { count: s.sources })}, ${s.pct}%`}
          </span>
        </li>
      ))}
    </ul>
  );
}
