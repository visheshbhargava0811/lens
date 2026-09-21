import type { SegmentKey } from "@/lib/coverage";

/** Color plus pattern per stance bucket. Keep in sync with tokens.css. */
export const stanceFill: Record<SegmentKey, string> = {
  critical: "bg-stance-critical pattern-hatch",
  balanced: "bg-stance-balanced",
  supportive: "bg-stance-supportive pattern-dots",
  unclassified: "bg-stance-unclassified pattern-light-hatch",
};
