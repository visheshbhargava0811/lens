import { useTranslations } from "next-intl";

import type { Coverage } from "@/lib/api/types";
import { segmentsFromCoverage, totalSources, type Segment } from "@/lib/coverage";
import { cn } from "@/lib/utils";

import { MethodologyLink } from "./MethodologyLink";
import { biasFill, biasInk } from "./bias-style";

/** sm: thin feed bar. md and lg: labelled bars with the share set inside each segment. */
const heights = { sm: "h-1.5", md: "h-6", lg: "h-7" } as const;

type Props = {
  coverage: Coverage;
  /** Distinct source count, used for the limited-coverage message. */
  sourceCount: number;
  size?: keyof typeof heights;
  showMeta?: boolean;
  /** Short text set beside a small bar, e.g. "56% critical of the government". */
  summary?: string;
  className?: string;
};

/**
 * Pure CSS outlet-bias bar. Segments are proportional to distinct sources.
 * Hover or focus shows a breakdown; screen readers get a full text alternative.
 */
export function CoverageBar({ coverage, sourceCount, size = "sm", showMeta = true, summary, className }: Props) {
  const t = useTranslations("coverage");
  const tc = useTranslations("confidence");
  const tp = useTranslations("bias.phrase");
  const ts = useTranslations("bias.short");

  if (!coverage.available) {
    return (
      <div className={cn("relative z-10", className)} data-testid="coverage-limited">
        <p className="rounded-control bg-surface px-3 py-2 text-sm text-ink-muted">
          {t("limited", { count: sourceCount, min: coverage.min_sources })}
        </p>
        {showMeta && (
          <MethodologyLink href={coverage.methodology_url} className="mt-1.5 inline-block">
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
  const labelled = size !== "sm";
  const alt = t("alt", {
    total,
    parts: visible.map((s) => t("altPart", { pct: s.pct, phrase: tp(s.key) })).join(", "),
    confidence,
  });

  return (
    <div className={cn("relative z-10", className)} data-testid="coverage-bar">
      <div className={cn("group/bar relative", summary && "flex items-center gap-3")}>
        <div
          role="img"
          aria-label={alt}
          tabIndex={0}
          className={cn(
            "flex gap-[2px] overflow-hidden rounded-[2px] bg-paper ring-1 ring-ink/15",
            summary ? "w-20 shrink-0" : "w-full",
            heights[size],
          )}
        >
          {visible.map((s) => (
            <Seg key={s.key} segment={s} label={labelled ? ts(s.key) : null} />
          ))}
        </div>
        {summary && <p className="min-w-0 text-xs font-medium text-ink">{summary}</p>}
        <div
          aria-hidden
          className="pointer-events-none invisible absolute start-0 top-full z-20 mt-2 w-max max-w-[18rem] translate-y-1 rounded-control bg-ink px-3 py-2 text-xs text-paper opacity-0 shadow-float transition-[opacity,transform,visibility] duration-150 ease-out group-focus-within/bar:visible group-focus-within/bar:translate-y-0 group-focus-within/bar:opacity-100 group-hover/bar:visible group-hover/bar:translate-y-0 group-hover/bar:opacity-100"
        >
          <ul className="space-y-0.5 tabular-nums">
            {visible.map((s) => (
              <li key={s.key}>{t("tooltip", { sources: s.sources, pct: s.pct, phrase: tp(s.key) })}</li>
            ))}
          </ul>
        </div>
      </div>
      {showMeta && (
        <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-ink-muted">
          <span>{t("confidence", { level: confidence })}</span>
          <MethodologyLink href={coverage.methodology_url}>{t("howCalculated")}</MethodologyLink>
        </div>
      )}
    </div>
  );
}

function Seg({ segment, label }: { segment: Segment; label: string | null }) {
  // Each segment is its own container: the label shows only where it fits, then the share alone.
  return (
    <span
      data-segment={segment.key}
      data-pct={segment.pct}
      className={cn(
        "@container flex h-full min-w-0 items-center justify-center overflow-hidden text-[0.6875rem] font-bold whitespace-nowrap tabular-nums",
        biasFill[segment.key],
        biasInk[segment.key],
      )}
      style={{ width: `${segment.pct}%` }}
    >
      {label !== null && (
        <span className="hidden @[2.25rem]:inline">
          <span className="hidden @[7.5rem]:inline">{label} </span>
          {segment.pct}%
        </span>
      )}
    </span>
  );
}
