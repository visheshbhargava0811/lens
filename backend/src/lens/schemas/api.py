"""Public API shapes (docs/09, ADR-0008, ADR-0009). The frontend client is generated from these.

The coverage bar counts distinct outlets by their outlet-level bias rating (Left / Center / Right)
from a named third-party rater (ADR-0020). G-BIAS-01: every bias and factuality figure carries
`confidence`, and `methodology_url` either on the same object or on its response envelope.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, Field, field_validator

Confidence = Literal["low", "medium", "high"]
BiasKey = Literal["left", "center", "right"]
StoryStatus = Literal["developing", "stable", "archived"]
AnalysisDepth = Literal["headline_only", "snippet", "full_text"]


class CoverageBucket(BaseModel):
    key: BiasKey
    sources: int
    pct: int


class SourcesPct(BaseModel):
    sources: int
    pct: int


class CoverageAvailable(BaseModel):
    available: Literal[True] = True
    basis: Literal["outlet_bias"] = "outlet_bias"
    buckets: list[CoverageBucket]
    unrated: SourcesPct  # outlets with no bias rating
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


class BiasBlindspot(BaseModel):
    type: Literal["bias"] = "bias"
    skew: BiasKey
    score: float


class LanguageBlindspot(BaseModel):
    type: Literal["language"] = "language"
    skew: str  # language group, e.g. "en" or "indic"
    score: float


Blindspot = Annotated[BiasBlindspot | LanguageBlindspot, Field(discriminator="type")]


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
    """A fact-checker's published verdict, never ours (docs/13): their name, their wording, their link."""

    claim: str
    fact_checker: str
    rating: str = Field(description="The fact-checker's own rating wording")
    rating_normalized: Literal["true", "false", "misleading", "unproven", "other"]
    match: Literal["same_claim", "related"] = Field(
        description="same_claim: this fact-check examines the claim; related: same event, different claim"
    )
    url: str
    published_at: datetime | None


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


class RatingRef(BaseModel):
    """An outlet rating as shown on an article row: "According to {rater}: {value}"."""

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
    analysis_depth: AnalysisDepth
    bias: Literal["left", "center", "right", "unrated"]  # bucket of source_bias, mapped as in the stats
    source_bias: RatingRef | None
    source_factuality: RatingRef | None
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
    type: Literal["bias", "language"]
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
    blindspot_bias_share: float
    blindspot_language_share: float
    feed_min_sources: int
    raters: list[Rater]


class SourceImportResult(BaseModel):
    ownership_added: int
    ratings_added: int
    unchanged: int


# ---------------------------------------------------------------- Ask (SSE events, docs/09)


class AskRequest(BaseModel):
    query: str = Field(min_length=1, max_length=500)
    session_id: str | None = Field(default=None, max_length=64)
    lang: str | None = Field(default=None, max_length=8)  # UI language; output language only

    @field_validator("query")
    @classmethod
    def _plain_text(cls, v: str) -> str:
        """Control characters (NUL included) are removed; the text stays data (G-IN-02 screens it next)."""
        v = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", v).strip()
        if not v:
            raise ValueError("empty question")
        return v


class AskStatus(BaseModel):
    step: Literal["understanding", "searching", "checking_sources", "writing", "verifying"]
    message: str


class AskUnderstanding(BaseModel):
    neutral_query: str
    removed_premises: list[str]
    language: str
    intent: str


class AskSource(BaseModel):
    source_id: str
    name: str
    language: str
    bias: Literal["left", "center", "right", "unrated"]  # outlet bucket (ADR-0020), as in ArticleRow


class AskEvidence(BaseModel):
    story_ids: list[str]
    sources: list[AskSource]
    stale: bool
    newest_article_at: datetime | None
    methodology_url: str


class AskArticle(BaseModel):
    """A cited article, so citation chips can show the headline and link (docs/09)."""

    id: str
    headline: str
    headline_lang: str
    url: str
    source_name: str
    source_language: str


class AskAnswer(BaseModel):
    """`answer_final`. Every sentence is cited and passed the checks; coverage is computed by code.
    `basis` is "stored_summary" when the live answer failed verification and the story's stored,
    already-verified summary is served instead (docs/06 fallback_precomputed)."""

    basis: Literal["live", "stored_summary"]
    lang: str  # language of the sentences: "hi" when localized and checked (G-OUT-06), else "en"
    tldr: list[CitedSentence]
    what_happened: list[CitedSentence]
    agreements: list[CitedSentence]
    disagreements: list[CitedSentence]
    premises_addressed: list[CitedSentence]
    limitations: list[str]
    follow_up_questions: list[str]
    coverage: CoverageAvailable | CoverageLimited
    fact_checks: list[FactCheckRef]
    story_ids: list[str]
    articles: list[AskArticle]
    verified: Literal[True]


class AskAbstain(BaseModel):
    reason: Literal[
        "insufficient_coverage", "out_of_scope", "sensitive_topic_under_review", "guard_block", "service_unavailable"
    ]
    message: str
    closest_stories: list[StoryCard]


class AskError(BaseModel):
    code: str
    message: str
    retry_after_s: int | None = None


class AskEvents(BaseModel):
    """Documentation only: the payload type of each `/ask` SSE event, keyed by event name, so the
    generated client has these types. The endpoint streams them as `event: <name>` / `data: <json>`."""

    status: AskStatus
    understanding: AskUnderstanding
    evidence: AskEvidence
    answer_final: AskAnswer
    abstain: AskAbstain
    error: AskError


# ---------------------------------------------------------------- memory (Phase 9, docs/11, ADR-0041)


class StoryChanges(BaseModel):
    """ "What changed since you last looked": built by code, never generated. Every item is an article or a
    fact-check published after the reader's previous view, so each one cites itself."""

    since: datetime
    new_articles: list[AskArticle]
    new_fact_checks: list[FactCheckRef]
    summary_updated: bool


class MeState(BaseModel):
    consented: bool
    preferences: dict[str, str | list[str]]
    allowed: dict[str, list[str]]  # the closed value set of every key: the whole storable surface


class MemoryStoryView(BaseModel):
    id: str
    story_id: str
    headline: str
    viewed_at: datetime


class MemoryAsk(BaseModel):
    id: str
    question: str  # PII-masked at storage (G-OUT-05)
    created_at: datetime


class MemoryView(BaseModel):
    """/me/memory: every stored item, each deletable (docs/11 hard rule 6)."""

    preferences: dict[str, str | list[str]]
    story_views: list[MemoryStoryView]
    ask_history: list[MemoryAsk]
    retention_days: int


class PreferenceUpdate(BaseModel):
    key: str
    value: str | list[str]
