/**
 * Coverage bar math. Pure functions, unit-tested: this is the number users see.
 * Segments are proportional to distinct sources (after syndication dedup), bucketed by each
 * outlet's third-party bias rating: Left, Center, Right, or Unrated (ADR-0020).
 */
import type { Coverage, BiasKey } from "@/lib/api/types";

export const BIAS_ORDER: readonly BiasKey[] = ["left", "center", "right"];
export const MIN_SOURCES_FOR_BAR = 4;

export type SegmentKey = BiasKey | "unrated";

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

/** Segments in display order: left, center, right, then unrated. */
export function coverageSegments(
  counts: Partial<Record<BiasKey, number>>,
  unrated: number,
): Segment[] {
  const keys: SegmentKey[] = [...BIAS_ORDER, "unrated"];
  const values = [...BIAS_ORDER.map((k) => counts[k] ?? 0), unrated];
  const pcts = percentages(values);
  return keys.map((key, i) => ({ key, sources: values[i], pct: pcts[i] }));
}

export function segmentsFromCoverage(coverage: Coverage): Segment[] {
  if (!coverage.available) return [];
  const counts = Object.fromEntries(coverage.buckets.map((b) => [b.key, b.sources]));
  return coverageSegments(counts, coverage.unrated.sources);
}

export function totalSources(segments: readonly Segment[]): number {
  return segments.reduce((a, s) => a + s.sources, 0);
}

/** A bar is shown only with at least `min` distinct sources (docs/01). */
export function isLimited(sourceCount: number, min = MIN_SOURCES_FOR_BAR): boolean {
  return sourceCount < min;
}

/** Build a Coverage object from raw counts. Used by fixtures; mirrors the backend (lens.services.stories). */
export function buildCoverage(
  counts: Record<BiasKey, number>,
  unrated: number,
  confidence: Coverage["confidence"],
  min = MIN_SOURCES_FOR_BAR,
): Coverage {
  const methodology_url = "/methodology#bias";
  const segments = coverageSegments(counts, unrated);
  if (isLimited(totalSources(segments), min)) {
    return { available: false, reason: "limited_coverage", min_sources: min, confidence, methodology_url };
  }
  const [left, center, right, unr] = segments;
  return {
    available: true,
    basis: "outlet_bias",
    buckets: [left, center, right].map((s) => ({ key: s.key as BiasKey, sources: s.sources, pct: s.pct })),
    unrated: { sources: unr.sources, pct: unr.pct },
    confidence,
    methodology_url,
  };
}
