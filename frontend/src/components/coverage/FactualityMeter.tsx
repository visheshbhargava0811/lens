import { useTranslations } from "next-intl";

import type { FactualityCounts } from "@/lib/api/types";
import { percentages } from "@/lib/coverage";
import { cn } from "@/lib/utils";

import { MethodologyLink } from "./MethodologyLink";

const levels = [
  { key: "high", fill: "bg-factuality-high" },
  { key: "mixed", fill: "bg-factuality-mixed" },
  { key: "low", fill: "bg-factuality-low" },
] as const;

/** Three-segment ink-scale bar with labels, counts and the Not rated count. */
export function FactualityMeter({ factuality }: { factuality: FactualityCounts }) {
  const t = useTranslations("factuality");
  const tc = useTranslations("confidence");
  const tcov = useTranslations("coverage");
  const counts = levels.map((l) => factuality[l.key]);
  const pcts = percentages(counts);
  const rated = counts.reduce((a, b) => a + b, 0);
  const alt = t("alt", { ...factuality, confidence: tc(factuality.confidence) });

  return (
    <div>
      {rated > 0 && (
        <div role="img" aria-label={alt} className="flex h-2 w-full gap-px overflow-hidden rounded-chip">
          {levels.map((l, i) =>
            counts[i] > 0 ? <span key={l.key} className={cn("h-full", l.fill)} style={{ width: `${pcts[i]}%` }} /> : null,
          )}
        </div>
      )}
      <dl className="mt-2 grid grid-cols-2 gap-x-4 gap-y-1 text-sm">
        {levels.map((l) => (
          <div key={l.key} className="flex items-center justify-between gap-2">
            <dt className="flex items-center gap-2">
              <span aria-hidden className={cn("size-2.5 rounded-full", l.fill)} />
              {t(l.key)}
            </dt>
            <dd className="tabular-nums">{factuality[l.key]}</dd>
          </div>
        ))}
        <div className="flex items-center justify-between gap-2">
          <dt className="flex items-center gap-2">
            <span aria-hidden className="size-2.5 rounded-full border border-ink-muted" />
            {t("notRated")}
          </dt>
          <dd className="tabular-nums">{factuality.unrated}</dd>
        </div>
      </dl>
      <div className="mt-2 flex flex-wrap items-center gap-x-3 text-xs text-ink-muted">
        <span>{tcov("confidence", { level: tc(factuality.confidence) })}</span>
        <MethodologyLink href={factuality.methodology_url}>{tcov("howCalculated")}</MethodologyLink>
      </div>
    </div>
  );
}
