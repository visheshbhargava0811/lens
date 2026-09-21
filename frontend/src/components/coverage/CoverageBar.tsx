import { useTranslations } from "next-intl";

import type { Coverage } from "@/lib/api/types";
import { segmentsFromCoverage, totalSources, type Segment } from "@/lib/coverage";
import { cn } from "@/lib/utils";

import { MethodologyLink } from "./MethodologyLink";
import { stanceFill } from "./stance-style";

const heights = { sm: "h-2", md: "h-3", lg: "h-3.5" } as const;

type Props = {
  coverage: Coverage;
  /** Distinct source count, used for the limited-coverage message. */
  sourceCount: number;
  size?: keyof typeof heights;
  showMeta?: boolean;
  className?: string;
};

/**
 * Pure CSS stance bar. Segments are proportional to distinct sources.
 * Hover or focus shows a breakdown; screen readers get a full text alternative.
 */
export function CoverageBar({ coverage, sourceCount, size = "sm", showMeta = true, className }: Props) {
  const t = useTranslations("coverage");
  const tc = useTranslations("confidence");
  const tp = useTranslations("stance.phrase");

  if (!coverage.available) {
    return (
      <div className={cn("relative z-10", className)} data-testid="coverage-limited">
        <p className="rounded-control bg-surface px-3 py-2 text-sm text-ink-muted">
          {t("limited", { count: sourceCount, min: coverage.min_sources })}
        </p>
        {showMeta && (
          <MethodologyLink href={coverage.methodology_url} className="mt-1 inline-block">
            {t("howCalculated")}
          </MethodologyLink>
        )}
      </div>
    );
  }

  const segments = segmentsFromCoverage(coverage);
  const visible = segments.filter((s) => s.sources > 0);
  const total = totalSources(segments);
  const confidence = tc(coverage.confidence);
  const alt = t("alt", {
    total,
    parts: visible.map((s) => t("altPart", { pct: s.pct, phrase: tp(s.key) })).join(", "),
    confidence,
  });

  return (
    <div className={cn("relative z-10", className)} data-testid="coverage-bar">
      <div className="group/bar relative">
        <div
          role="img"
          aria-label={alt}
          tabIndex={0}
          className={cn("flex w-full gap-px overflow-hidden rounded-chip bg-paper", heights[size])}
        >
          {visible.map((s) => (
            <Seg key={s.key} segment={s} />
          ))}
        </div>
        <div
          aria-hidden
          className="pointer-events-none invisible absolute start-0 top-full z-20 mt-2 w-max max-w-[18rem] rounded-control bg-ink px-3 py-2 text-xs text-paper shadow-float group-focus-within/bar:visible group-hover/bar:visible"
        >
          <ul className="space-y-0.5">
            {visible.map((s) => (
              <li key={s.key}>{t("tooltip", { sources: s.sources, pct: s.pct, phrase: tp(s.key) })}</li>
            ))}
          </ul>
        </div>
      </div>
      {showMeta && (
        <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-ink-muted">
          <span>{t("confidence", { level: confidence })}</span>
          <MethodologyLink href={coverage.methodology_url}>{t("howCalculated")}</MethodologyLink>
        </div>
      )}
    </div>
  );
}

function Seg({ segment }: { segment: Segment }) {
  return (
    <span
      data-segment={segment.key}
      data-pct={segment.pct}
      className={cn("h-full", stanceFill[segment.key])}
      style={{ width: `${segment.pct}%` }}
    />
  );
}
