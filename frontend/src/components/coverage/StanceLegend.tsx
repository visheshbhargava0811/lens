import { useTranslations } from "next-intl";

import type { Coverage, StanceTarget } from "@/lib/api/types";
import { segmentsFromCoverage } from "@/lib/coverage";
import { cn } from "@/lib/utils";

import { stanceFill } from "./stance-style";

/** Swatch plus pattern plus label plus count and share. */
export function StanceLegend({
  coverage,
  target = "central_govt",
  compact = false,
}: {
  coverage: Coverage;
  target?: StanceTarget;
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
          <span aria-hidden className={cn("size-3 shrink-0 rounded-[3px]", stanceFill[s.key])} />
          <span className={compact ? "" : "flex-1"}>{t(`stance.label.${s.key}`, { target })}</span>
          <span className="tabular-nums text-ink-muted">
            {compact ? `${s.pct}%` : `${t("coverage.sources", { count: s.sources })}, ${s.pct}%`}
          </span>
        </li>
      ))}
    </ul>
  );
}
