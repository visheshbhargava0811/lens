/**
 * API shapes (docs/09_API_SPEC.md), aliased from the generated OpenAPI types in `../api-types.ts`
 * (`make gen-client`). Components and MSW fixtures import from here, so any drift between the
 * backend models and the fixtures fails `tsc`.
 */
import type { components } from "../api-types";

type S = components["schemas"];

export type Confidence = S["CoverageAvailable"]["confidence"];
/** Outlet bias bucket from a third-party rater (ADR-0020). */
export type BiasKey = S["CoverageBucket"]["key"];
export type StoryStatus = S["StoryCard"]["status"];
export type AnalysisDepth = S["ArticleRow"]["analysis_depth"];

export type CoverageBucket = S["CoverageBucket"];
export type Coverage = S["CoverageAvailable"] | S["CoverageLimited"];
export type FactualityCounts = S["FactualityCounts"];
export type Blindspot = S["BiasBlindspot"] | S["LanguageBlindspot"];
export type RatingRef = S["RatingRef"];
export type StoryCard = S["StoryCard"];
export type Citation = S["Citation"];
export type CitedSentence = S["CitedSentence"];
export type StorySummary = S["StorySummary"];
export type FactCheck = S["FactCheckRef"];
export type Ownership = S["Ownership"];
export type StoryDetail = S["StoryDetail"];
export type ArticleRow = S["ArticleRow"];
export type StoryArticles = S["StoryArticles"];
export type Blindspots = S["Blindspots"];
export type Topic = S["Topic"];
export type Methodology = S["Methodology"];
export type SourceDetail = S["SourceDetail"];

/** docs/09 pagination envelope; `/feed` returns Page<StoryCard> (ADR-0009). */
export interface Page<T> {
  items: T[];
  next_cursor: string | null;
}

export interface ApiError {
  error: { code: string; message: string; retry_after_s?: number | null };
}
