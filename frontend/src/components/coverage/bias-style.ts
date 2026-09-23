import type { SegmentKey } from "@/lib/coverage";

/** Color plus pattern per bias bucket (not party colors, docs/10). Keep in sync with tokens.css. */
export const biasFill: Record<SegmentKey, string> = {
  left: "bg-bias-left pattern-hatch",
  center: "bg-bias-center",
  right: "bg-bias-right pattern-dots",
  unrated: "bg-bias-unrated pattern-light-hatch",
};

/** Text color for labels set inside a segment. */
export const biasInk: Record<SegmentKey, string> = {
  left: "text-bias-left-ink",
  center: "text-bias-center-ink",
  right: "text-bias-right-ink",
  unrated: "text-bias-unrated-ink",
};
