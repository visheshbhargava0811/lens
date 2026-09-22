import type { SegmentKey } from "@/lib/coverage";

/** Color plus pattern per stance bucket. Keep in sync with tokens.css. */
export const stanceFill: Record<SegmentKey, string> = {
  critical: "bg-stance-critical pattern-hatch",
  balanced: "bg-stance-balanced",
  supportive: "bg-stance-supportive pattern-dots",
  unclassified: "bg-stance-unclassified pattern-light-hatch",
};

/** Text color for labels set inside a segment. */
export const stanceInk: Record<SegmentKey, string> = {
  critical: "text-stance-critical-ink",
  balanced: "text-stance-balanced-ink",
  supportive: "text-stance-supportive-ink",
  unclassified: "text-stance-unclassified-ink",
};
