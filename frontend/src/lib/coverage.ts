/**
 * Coverage bar math. Pure functions, unit-tested: this is the number users see.
 * Segments are proportional to distinct sources (after syndication dedup).
 */
import type { Coverage, StanceKey } from "@/lib/api/types";

export const STANCE_ORDER: readonly StanceKey[] = ["critical", "balanced", "supportive"];
export const MIN_SOURCES_FOR_BAR = 4;

export type SegmentKey = StanceKey | "unclassified";

export interface Segment {
  key: SegmentKey;
  sources: number;
  pct: number;
}

/**
 * Integer percentages that always sum to 100 (largest-remainder method).
 * Ties in the remainder go to the earlier entry, so the result is deterministic.
 * Returns all zeros when the total is zero.
 */
export function percentages(counts: readonly number[]): number[] {
  if (counts.some((c) => c < 0 || !Number.isFinite(c))) {
    throw new Error("counts must be finite and non-negative");
  }
  const total = counts.reduce((a, b) => a + b, 0);
  if (total === 0) return counts.map(() => 0);

  const exact = counts.map((c) => (c * 100) / total);
  const floors = exact.map(Math.floor);
  let remaining = 100 - floors.reduce((a, b) => a + b, 0);
  const order = exact
    .map((x, i) => ({ i, rem: x - Math.floor(x) }))
    .sort((a, b) => b.rem - a.rem || a.i - b.i);
  for (const { i } of order) {
    if (remaining === 0) break;
    floors[i] += 1;
    remaining -= 1;
  }
  return floors;
}

/** Segments in display order: critical, balanced, supportive, then unclassified. */
export function coverageSegments(
  counts: Partial<Record<StanceKey, number>>,
  unclassified: number,
): Segment[] {
  const keys: SegmentKey[] = [...STANCE_ORDER, "unclassified"];
  const values = [...STANCE_ORDER.map((k) => counts[k] ?? 0), unclassified];
  const pcts = percentages(values);
  return keys.map((key, i) => ({ key, sources: values[i], pct: pcts[i] }));
}

export function segmentsFromCoverage(coverage: Coverage): Segment[] {
  if (!coverage.available) return [];
  const counts = Object.fromEntries(coverage.buckets.map((b) => [b.key, b.sources]));
  return coverageSegments(counts, coverage.unclassified.sources);
}

export function totalSources(segments: readonly Segment[]): number {
  return segments.reduce((a, s) => a + s.sources, 0);
}

/** A bar is shown only with at least `min` distinct sources (docs/01). */
export function isLimited(sourceCount: number, min = MIN_SOURCES_FOR_BAR): boolean {
  return sourceCount < min;
}

/** Build a Coverage object from raw counts. Used by fixtures now and mirrored by the backend in Phase 3. */
export function buildCoverage(
  counts: Record<StanceKey, number>,
  unclassified: number,
  confidence: Coverage["confidence"],
  min = MIN_SOURCES_FOR_BAR,
): Coverage {
  const methodology_url = "/methodology#stance";
  const segments = coverageSegments(counts, unclassified);
  if (isLimited(totalSources(segments), min)) {
    return { available: false, reason: "limited_coverage", min_sources: min, confidence, methodology_url };
  }
  const [critical, balanced, supportive, unc] = segments;
  return {
    available: true,
    basis: "article_stance",
    buckets: [critical, balanced, supportive].map((s) => ({
      key: s.key as StanceKey,
      sources: s.sources,
      pct: s.pct,
    })),
    unclassified: { sources: unc.sources, pct: unc.pct },
    confidence,
    methodology_url,
  };
}

/** Bucket for one article. Low confidence and not_applicable count as unclassified (docs/01). */
export function articleBucket(stance: { value: string; confidence: string }): SegmentKey {
  if (stance.confidence === "low") return "unclassified";
  if (stance.value === "critical" || stance.value === "balanced" || stance.value === "supportive") {
    return stance.value;
  }
  return "unclassified";
}

/** The government most articles in a story are about, for legend labels. Ties go to central_govt. */
export function dominantTarget(
  articles: readonly { stance: { target: "central_govt" | "state_govt" | "opposition" | "none" } }[],
): "central_govt" | "state_govt" | "opposition" {
  const counts = { central_govt: 0, state_govt: 0, opposition: 0 };
  for (const a of articles) if (a.stance.target !== "none") counts[a.stance.target] += 1;
  const order = ["central_govt", "state_govt", "opposition"] as const;
  return order.reduce((best, k) => (counts[k] > counts[best] ? k : best), order[0]);
}
