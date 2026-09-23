"""Public API shapes (docs/09, ADR-0008, ADR-0009). The frontend client is generated from these.

G-BIAS-01: every coverage, stance and factuality figure carries `confidence`, and
`methodology_url` either on the same object or on its response envelope.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, Field

Confidence = Literal["low", "medium", "high"]
StanceKey = Literal["critical", "balanced", "supportive"]
StanceValue = Literal["critical", "balanced", "supportive", "not_applicable", "unclassified"]
StanceTarget = Literal["central_govt", "state_govt", "opposition", "none"]
StoryStatus = Literal["developing", "stable", "archived"]
AnalysisDepth = Literal["headline_only", "snippet", "full_text"]


class CoverageBucket(BaseModel):
    key: StanceKey
    sources: int
    pct: int


class SourcesPct(BaseModel):
    sources: int
    pct: int


class CoverageAvailable(BaseModel):
    available: Literal[True] = True
    basis: Literal["article_stance"] = "article_stance"
    buckets: list[CoverageBucket]
    unclassified: SourcesPct
    confidence: Confidence
    methodology_url: str


class CoverageLimited(BaseModel):
    available: Literal[False] = False
    reason: Literal["limited_coverage"] = "limited_coverage"
    min_sources: int
    confidence: Confidence
    methodology_url: str


class FactualityCounts(BaseModel):
    high: int
    mixed: int
    low: int
    unrated: int
    confidence: Confidence
    methodology_url: str


class StanceBlindspot(BaseModel):
    type: Literal["stance"] = "stance"
    skew: StanceKey
    score: float


class LanguageBlindspot(BaseModel):
    type: Literal["language"] = "language"
    skew: str  # language group, e.g. "en" or "indic"
    score: float


Blindspot = Annotated[StanceBlindspot | LanguageBlindspot, Field(discriminator="type")]


class StoryImage(BaseModel):
    url: str
    source_name: str


class Counts(BaseModel):
    sources: int
    articles: int
    by_language: dict[str, int]


class StoryCard(BaseModel):
    id: str
    slug: str
    headline: str
    headline_lang: str
    status: StoryStatus
    updated_at: datetime
    topic: str | None
    image: StoryImage | None
    counts: Counts
    coverage: CoverageAvailable | CoverageLimited
    factuality: FactualityCounts
    blindspot: Blindspot | None
    summary_preview: str | None


class Citation(BaseModel):
    n: int
    article_id: str
    source_name: str
    chunk_id: str


class CitedSentence(BaseModel):
    text: str
    citations: list[Citation]


class StorySummary(BaseModel):
    lang: str
    version: int
    generated_at: datetime
    verified: bool
    sentences: list[CitedSentence]
    agreements: list[CitedSentence]
    disagreements: list[CitedSentence]


class FactCheckRef(BaseModel):
    claim: str
    fact_checker: str
    rating: str
    url: str
    published_at: datetime


class OwnershipGroup(BaseModel):
    name: str
    sources: int


class Ownership(BaseModel):
    groups: list[OwnershipGroup]
    unknown: int
    methodology_url: str


class StoryDetail(BaseModel):
    story: StoryCard
    summary: StorySummary | None
    framing_differences: list[CitedSentence]
    fact_checks: list[FactCheckRef]
    ownership: Ownership
    limitations: list[str]


class ArticleSource(BaseModel):
    id: str
    name: str
    logo_url: str | None
    language: str


class ArticleStance(BaseModel):
    value: StanceValue
    target: StanceTarget
    confidence: Confidence


class SourceFactuality(BaseModel):
    rater: str
    value: str
    method_url: str
    confidence: Confidence


class SourceOwnershipRef(BaseModel):
    owner: str
    evidence_url: str


class ArticleRow(BaseModel):
    id: str
    source: ArticleSource
    headline: str
    headline_lang: str
    published_at: datetime
    url: str
    stance: ArticleStance
    analysis_depth: AnalysisDepth
    source_factuality: SourceFactuality | None
    source_ownership: SourceOwnershipRef | None
    is_syndicated: bool
    also_carried_by: list[str]


class StoryCardPage(BaseModel):
    items: list[StoryCard]
    next_cursor: str | None


class StoryArticles(BaseModel):
    items: list[ArticleRow]
    methodology_url: str


class Blindspots(BaseModel):
    type: Literal["stance", "language"]
    items: list[StoryCard]
    methodology_url: str


class Topic(BaseModel):
    slug: str
    name: str


class Topics(BaseModel):
    items: list[Topic]


# ---- sources (shape not fixed by docs/09; ADR-0018)


class SourceSummary(BaseModel):
    id: str
    slug: str
    name: str
    homepage_url: str
    languages: list[str]
    region: str | None
    is_wire: bool
    license_mode: Literal["full_text", "snippet_only", "link_only"]


class SourceList(BaseModel):
    items: list[SourceSummary]


class OwnershipRecord(BaseModel):
    owner_name: str
    owner_type: str | None
    parent_group: str | None
    evidence_url: str
    retrieved_at: datetime
    confidence: Confidence


class RatingRecord(BaseModel):
    dimension: str
    rater: str
    value: str
    method_url: str
    evidence_url: str | None
    retrieved_at: datetime
    confidence: Confidence


class SourceDetail(BaseModel):
    source: SourceSummary
    ownership: list[OwnershipRecord]
    ratings: list[RatingRecord]
    recent_stories: list[StoryCard]
    methodology_url: str


# ---- methodology: live parameters; the prose lives in the translated UI messages


class Rater(BaseModel):
    rater: str
    dimension: str
    method_url: str
    sources_rated: int


class Methodology(BaseModel):
    min_sources_for_bar: int
    min_sources_for_blindspot: int
    blindspot_stance_share: float
    blindspot_language_share: float
    feed_min_sources: int
    raters: list[Rater]


class SourceImportResult(BaseModel):
    ownership_added: int
    ratings_added: int
    unchanged: int
