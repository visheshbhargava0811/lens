/**
 * API shapes from docs/09_API_SPEC.md. Hand-written until the backend exposes these
 * endpoints (Phase 3); then they are replaced by `make gen-client` output.
 */

export type Confidence = "low" | "medium" | "high";
export type StanceKey = "critical" | "balanced" | "supportive";
export type StanceValue = StanceKey | "not_applicable" | "unclassified";
export type StanceTarget = "central_govt" | "state_govt" | "opposition" | "none";
export type StoryStatus = "developing" | "stable" | "archived";
export type AnalysisDepth = "headline_only" | "snippet" | "full_text";

export interface CoverageBucket {
  key: StanceKey;
  sources: number;
  pct: number;
}

export type Coverage =
  | {
      available: true;
      basis: "article_stance";
      buckets: CoverageBucket[];
      unclassified: { sources: number; pct: number };
      confidence: Confidence;
      methodology_url: string;
    }
  | {
      available: false;
      reason: "limited_coverage";
      min_sources: number;
      confidence: Confidence;
      methodology_url: string;
    };

export interface FactualityCounts {
  high: number;
  mixed: number;
  low: number;
  unrated: number;
  /** Not in the docs/09 example; added so G-BIAS-01 holds (docs/DECISIONS.md, ADR-0008). */
  confidence: Confidence;
  methodology_url: string;
}

export type Blindspot =
  | { type: "stance"; skew: StanceKey; score: number }
  | { type: "language"; skew: string; score: number };

export interface StoryCard {
  id: string;
  slug: string;
  headline: string;
  headline_lang: string;
  status: StoryStatus;
  updated_at: string;
  topic: string | null;
  image: { url: string; source_name: string } | null;
  counts: { sources: number; articles: number; by_language: Record<string, number> };
  coverage: Coverage;
  factuality: FactualityCounts;
  blindspot: Blindspot | null;
  summary_preview: string | null;
}

export interface Citation {
  n: number;
  article_id: string;
  source_name: string;
  chunk_id: string;
}

export interface CitedSentence {
  text: string;
  citations: Citation[];
}

export interface StorySummary {
  lang: string;
  version: number;
  generated_at: string;
  verified: boolean;
  sentences: CitedSentence[];
  agreements: CitedSentence[];
  disagreements: CitedSentence[];
}

export interface FactCheck {
  claim: string;
  fact_checker: string;
  rating: string;
  url: string;
  published_at: string;
}

export interface Ownership {
  groups: { name: string; sources: number }[];
  unknown: number;
  methodology_url: string;
}

export interface StoryDetail {
  story: StoryCard;
  summary: StorySummary | null;
  framing_differences: CitedSentence[];
  fact_checks: FactCheck[];
  ownership: Ownership;
  limitations: string[];
}

export interface ArticleRow {
  id: string;
  source: { id: string; name: string; logo_url: string | null; language: string };
  headline: string;
  headline_lang: string;
  published_at: string;
  url: string;
  stance: { value: StanceValue; target: StanceTarget; confidence: Confidence };
  analysis_depth: AnalysisDepth;
  source_factuality: { rater: string; value: string; method_url: string; confidence: Confidence } | null;
  source_ownership: { owner: string; evidence_url: string } | null;
  is_syndicated: boolean;
  also_carried_by: string[];
}

/** Envelope shapes. docs/09 fixes the item shapes; these wrappers follow its conventions. */
export interface Page<T> {
  items: T[];
  next_cursor: string | null;
}

export interface StoryArticles {
  items: ArticleRow[];
  methodology_url: string;
}

export interface Blindspots {
  type: "stance" | "language";
  items: StoryCard[];
  methodology_url: string;
}

export interface Topic {
  slug: string;
  name: string;
}

export interface ApiError {
  error: { code: string; message: string; retry_after_s?: number };
}
