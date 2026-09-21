import { describe, expect, it } from "vitest";

import {
  buildCoverage,
  coverageSegments,
  isLimited,
  percentages,
  segmentsFromCoverage,
  totalSources,
} from "@/lib/coverage";

const sum = (xs: number[]) => xs.reduce((a, b) => a + b, 0);

describe("percentages", () => {
  it("matches the docs/09 example", () => {
    expect(percentages([18, 12, 9, 3])).toEqual([43, 29, 21, 7]);
  });

  it("always sums to 100", () => {
    for (const counts of [[1, 1, 1], [2, 2, 2, 1], [7, 0, 0, 0], [1, 2, 3, 4, 5], [33, 33, 33, 1], [1, 1, 1, 1, 1, 1, 1]]) {
      expect(sum(percentages(counts))).toBe(100);
    }
  });

  it("breaks remainder ties toward the earlier entry, deterministically", () => {
    expect(percentages([1, 1, 1])).toEqual([34, 33, 33]);
    expect(percentages([1, 1, 1])).toEqual(percentages([1, 1, 1]));
  });

  it("returns zeros for an empty total", () => {
    expect(percentages([0, 0, 0, 0])).toEqual([0, 0, 0, 0]);
  });

  it("keeps zero-count entries at zero", () => {
    expect(percentages([5, 0, 5, 0])).toEqual([50, 0, 50, 0]);
  });

  it("rejects negative counts", () => {
    expect(() => percentages([1, -1])).toThrow();
  });
});

describe("coverageSegments", () => {
  it("orders critical, balanced, supportive, unclassified and includes unclassified share", () => {
    const segs = coverageSegments({ critical: 18, balanced: 12, supportive: 9 }, 3);
    expect(segs.map((s) => s.key)).toEqual(["critical", "balanced", "supportive", "unclassified"]);
    expect(segs.map((s) => s.pct)).toEqual([43, 29, 21, 7]);
    expect(totalSources(segs)).toBe(42);
  });

  it("treats missing buckets as zero", () => {
    const segs = coverageSegments({ critical: 2 }, 2);
    expect(segs.map((s) => s.sources)).toEqual([2, 0, 0, 2]);
    expect(segs.map((s) => s.pct)).toEqual([50, 0, 0, 50]);
  });

  it("handles a story that is entirely unclassified", () => {
    const segs = coverageSegments({}, 6);
    expect(segs.at(-1)).toMatchObject({ key: "unclassified", pct: 100 });
  });
});

describe("limited coverage", () => {
  it("is limited below min_sources and not at it", () => {
    expect(isLimited(3)).toBe(true);
    expect(isLimited(4)).toBe(false);
    expect(isLimited(5, 6)).toBe(true);
  });

  it("buildCoverage returns the limited shape below the threshold", () => {
    const cov = buildCoverage({ critical: 1, balanced: 1, supportive: 0 }, 0, "low");
    expect(cov).toMatchObject({ available: false, reason: "limited_coverage", min_sources: 4 });
    expect(segmentsFromCoverage(cov)).toEqual([]);
  });

  it("buildCoverage counts unclassified toward min_sources", () => {
    const cov = buildCoverage({ critical: 1, balanced: 1, supportive: 0 }, 2, "low");
    expect(cov.available).toBe(true);
  });

  it("buildCoverage round-trips through segmentsFromCoverage", () => {
    const cov = buildCoverage({ critical: 18, balanced: 12, supportive: 9 }, 3, "medium");
    expect(segmentsFromCoverage(cov).map((s) => s.pct)).toEqual([43, 29, 21, 7]);
    if (!cov.available) throw new Error("expected available");
    expect(sum([...cov.buckets.map((b) => b.pct), cov.unclassified.pct])).toBe(100);
  });
});
