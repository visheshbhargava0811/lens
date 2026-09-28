"""SQLAlchemy models. Reference DDL: docs/03_DATA_MODEL.md. Keep names in sync with it."""

import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    REAL,
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.dialects.postgresql import ENUM as PGEnum
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


# ---------------------------------------------------------------- enums


class LicenseMode(enum.StrEnum):
    full_text = "full_text"
    snippet_only = "snippet_only"
    link_only = "link_only"


class ImagePolicy(enum.StrEnum):
    hotlink = "hotlink"
    none = "none"


class Stance(enum.StrEnum):
    critical = "critical"
    balanced = "balanced"
    supportive = "supportive"
    not_applicable = "not_applicable"
    unclassified = "unclassified"


class StanceTarget(enum.StrEnum):
    central_govt = "central_govt"
    state_govt = "state_govt"
    opposition = "opposition"
    none = "none"


class Confidence(enum.StrEnum):
    low = "low"
    medium = "medium"
    high = "high"


class StoryStatus(enum.StrEnum):
    developing = "developing"
    stable = "stable"
    archived = "archived"


class AnalysisDepth(enum.StrEnum):
    headline_only = "headline_only"
    snippet = "snippet"
    full_text = "full_text"


def _pg_enum(e: type[enum.StrEnum], name: str) -> PGEnum:
    return PGEnum(e, name=name, values_callable=lambda cls: [m.value for m in cls])


license_mode_t = _pg_enum(LicenseMode, "license_mode")
image_policy_t = _pg_enum(ImagePolicy, "image_policy")
stance_t = _pg_enum(Stance, "stance")
stance_target_t = _pg_enum(StanceTarget, "stance_target")
confidence_t = _pg_enum(Confidence, "confidence")
story_status_t = _pg_enum(StoryStatus, "story_status")
analysis_depth_t = _pg_enum(AnalysisDepth, "analysis_depth")


# ---------------------------------------------------------------- helpers


def _pk() -> Mapped[uuid.UUID]:
    return mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))


def _fk(target: str, *, ondelete: str | None = None, nullable: bool = False) -> Mapped[Any]:
    return mapped_column(UUID(as_uuid=True), ForeignKey(target, ondelete=ondelete), nullable=nullable)


def _now() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


TSTZ = DateTime(timezone=True)


# ---------------------------------------------------------------- sources and metadata


class Source(Base):
    __tablename__ = "sources"

    id: Mapped[uuid.UUID] = _pk()
    slug: Mapped[str] = mapped_column(Text, unique=True)
    name: Mapped[str] = mapped_column(Text)
    homepage_url: Mapped[str] = mapped_column(Text)
    language_codes: Mapped[list[str]] = mapped_column(ARRAY(Text))
    country: Mapped[str] = mapped_column(Text, server_default="IN")
    region: Mapped[str | None] = mapped_column(Text)
    feed_urls: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, server_default=text("'[]'::jsonb"))
    license_mode: Mapped[LicenseMode] = mapped_column(license_mode_t, server_default=LicenseMode.snippet_only.value)
    image_policy: Mapped[ImagePolicy] = mapped_column(image_policy_t, server_default=ImagePolicy.none.value)
    robots_ok: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    is_wire: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    is_fact_checker: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    created_at: Mapped[datetime] = _now()
    # Not in the docs/03 DDL (ADR-0012): why a source is inactive, and where its feeds were found.
    inactive_reason: Mapped[str | None] = mapped_column(Text)
    evidence: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))


class SourceFetchState(Base):
    """Per-feed polling state: conditional-GET validators, schedule and health (ADR-0012)."""

    __tablename__ = "source_fetch_state"

    source_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sources.id", ondelete="CASCADE"), primary_key=True
    )
    feed_url: Mapped[str] = mapped_column(Text, primary_key=True)
    kind: Mapped[str] = mapped_column(Text)  # rss | sitemap
    interval_min: Mapped[int] = mapped_column(Integer, server_default=text("15"))
    next_fetch_at: Mapped[datetime] = mapped_column(TSTZ, server_default=func.now())
    etag: Mapped[str | None] = mapped_column(Text)
    last_modified: Mapped[str | None] = mapped_column(Text)
    last_fetched_at: Mapped[datetime | None] = mapped_column(TSTZ)
    last_success_at: Mapped[datetime | None] = mapped_column(TSTZ)
    last_status: Mapped[int | None] = mapped_column(Integer)
    last_error: Mapped[str | None] = mapped_column(Text)
    consecutive_failures: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    last_items: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    last_new: Mapped[int] = mapped_column(Integer, server_default=text("0"))


class SourceOwnership(Base):
    __tablename__ = "source_ownership"

    id: Mapped[uuid.UUID] = _pk()
    source_id: Mapped[uuid.UUID] = _fk("sources.id")
    owner_name: Mapped[str] = mapped_column(Text)
    owner_type: Mapped[str | None] = mapped_column(Text)
    parent_group: Mapped[str | None] = mapped_column(Text)
    evidence_url: Mapped[str] = mapped_column(Text)
    retrieved_at: Mapped[datetime] = mapped_column(TSTZ)
    verified_by: Mapped[str | None] = mapped_column(Text)
    confidence: Mapped[Confidence] = mapped_column(confidence_t)


class SourceRating(Base):
    __tablename__ = "source_ratings"
    __table_args__ = (Index(None, "source_id", "dimension"),)

    id: Mapped[uuid.UUID] = _pk()
    source_id: Mapped[uuid.UUID] = _fk("sources.id")
    dimension: Mapped[str] = mapped_column(Text)
    rater: Mapped[str] = mapped_column(Text)
    value: Mapped[str] = mapped_column(Text)
    numeric_value: Mapped[float | None] = mapped_column(REAL)
    method_url: Mapped[str] = mapped_column(Text)
    evidence_url: Mapped[str | None] = mapped_column(Text)
    retrieved_at: Mapped[datetime] = mapped_column(TSTZ)
    confidence: Mapped[Confidence] = mapped_column(confidence_t)


# ---------------------------------------------------------------- articles and chunks


class Article(Base):
    __tablename__ = "articles"
    __table_args__ = (
        UniqueConstraint("source_id", "url"),
        Index("ix_articles_published_at", text("published_at DESC")),
        Index("ix_articles_source_id_published_at", "source_id", text("published_at DESC")),
        Index(None, "simhash"),
    )

    id: Mapped[uuid.UUID] = _pk()
    source_id: Mapped[uuid.UUID] = _fk("sources.id")
    url: Mapped[str] = mapped_column(Text)
    canonical_url: Mapped[str] = mapped_column(Text, unique=True)
    title: Mapped[str] = mapped_column(Text)
    snippet: Mapped[str | None] = mapped_column(Text)
    full_text: Mapped[str | None] = mapped_column(Text)
    analysis_depth: Mapped[AnalysisDepth] = mapped_column(analysis_depth_t)
    language: Mapped[str] = mapped_column(Text)
    language_conf: Mapped[float | None] = mapped_column(REAL)
    published_at: Mapped[datetime] = mapped_column(TSTZ)
    fetched_at: Mapped[datetime] = _now()
    byline: Mapped[str | None] = mapped_column(Text)
    content_hash: Mapped[str] = mapped_column(Text)
    simhash: Mapped[int | None] = mapped_column(BigInteger)
    is_news: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    is_syndicated: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    # Not in docs/03 (ADR-0012): opinion pieces are kept but excluded from the coverage bar (docs/04).
    is_opinion: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    syndicated_from: Mapped[str | None] = mapped_column(Text)
    original_article_id: Mapped[uuid.UUID | None] = _fk("articles.id", nullable=True)
    image_url: Mapped[str | None] = mapped_column(Text)
    entities: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    event_type: Mapped[str | None] = mapped_column(Text)
    schema_version: Mapped[str] = mapped_column(Text)


class Chunk(Base):
    __tablename__ = "chunks"
    __table_args__ = (UniqueConstraint("article_id", "idx"),)

    id: Mapped[uuid.UUID] = _pk()
    article_id: Mapped[uuid.UUID] = _fk("articles.id", ondelete="CASCADE")
    idx: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)
    char_start: Mapped[int] = mapped_column(Integer)
    char_end: Mapped[int] = mapped_column(Integer)
    token_count: Mapped[int] = mapped_column(Integer)
    qdrant_point_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))


# ---------------------------------------------------------------- stories


class Story(Base):
    __tablename__ = "stories"
    __table_args__ = (
        Index("ix_stories_last_updated_at", text("last_updated_at DESC")),
        Index("ix_stories_topic_last_updated_at", "topic", text("last_updated_at DESC")),
    )

    id: Mapped[uuid.UUID] = _pk()
    slug: Mapped[str] = mapped_column(Text, unique=True)
    headline: Mapped[str] = mapped_column(Text)
    headline_lang: Mapped[str] = mapped_column(Text)
    status: Mapped[StoryStatus] = mapped_column(story_status_t, server_default=StoryStatus.developing.value)
    topic: Mapped[str | None] = mapped_column(Text)
    region: Mapped[str | None] = mapped_column(Text)
    first_seen_at: Mapped[datetime] = mapped_column(TSTZ)
    last_updated_at: Mapped[datetime] = mapped_column(TSTZ)
    article_count: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    source_count: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    languages: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default=text("'{}'"))
    kill_switch: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    review_status: Mapped[str] = mapped_column(Text, server_default="auto")


class StoryArticle(Base):
    __tablename__ = "story_articles"

    story_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("stories.id", ondelete="CASCADE"), primary_key=True
    )
    article_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("articles.id", ondelete="CASCADE"), primary_key=True
    )
    similarity: Mapped[float | None] = mapped_column(REAL)
    method: Mapped[str] = mapped_column(Text)
    assigned_at: Mapped[datetime] = _now()


class StoryStats(Base):
    __tablename__ = "story_stats"

    story_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("stories.id", ondelete="CASCADE"), primary_key=True
    )
    computed_at: Mapped[datetime] = mapped_column(TSTZ)
    bias_counts: Mapped[dict[str, int]] = mapped_column(JSONB)  # outlet Left/Center/Right (ADR-0020)
    factuality_counts: Mapped[dict[str, int]] = mapped_column(JSONB)
    ownership_counts: Mapped[dict[str, int]] = mapped_column(JSONB)
    language_counts: Mapped[dict[str, int]] = mapped_column(JSONB)
    coverage_confidence: Mapped[Confidence] = mapped_column(confidence_t)
    blindspot_type: Mapped[str | None] = mapped_column(Text)
    blindspot_skew: Mapped[str | None] = mapped_column(Text)
    blindspot_score: Mapped[float | None] = mapped_column(REAL)


# ---------------------------------------------------------------- analysis outputs


class Claim(Base):
    __tablename__ = "claims"
    __table_args__ = (Index("ix_claims_article_id", "article_id"),)

    id: Mapped[uuid.UUID] = _pk()
    article_id: Mapped[uuid.UUID] = _fk("articles.id", ondelete="CASCADE")
    text: Mapped[str] = mapped_column(Text)
    source_quote: Mapped[str] = mapped_column(Text)
    char_start: Mapped[int] = mapped_column(Integer)
    char_end: Mapped[int] = mapped_column(Integer)
    attributed_to: Mapped[str | None] = mapped_column(Text)
    checkable: Mapped[bool] = mapped_column(Boolean)
    schema_version: Mapped[str] = mapped_column(Text)
    prompt_version: Mapped[str | None] = mapped_column(Text)
    factcheck_checked_at: Mapped[datetime | None] = mapped_column(TSTZ)


class Framing(Base):
    __tablename__ = "framings"
    __table_args__ = (UniqueConstraint("article_id", "story_id"),)

    id: Mapped[uuid.UUID] = _pk()
    article_id: Mapped[uuid.UUID] = _fk("articles.id", ondelete="CASCADE")
    story_id: Mapped[uuid.UUID] = _fk("stories.id", ondelete="CASCADE")
    rationale: Mapped[str] = mapped_column(Text)
    headline_framing: Mapped[str] = mapped_column(Text)
    tone: Mapped[str] = mapped_column(Text)
    stance_target: Mapped[StanceTarget] = mapped_column(stance_target_t)
    stance: Mapped[Stance] = mapped_column(stance_t)
    stance_confidence: Mapped[Confidence] = mapped_column(confidence_t)
    emphasized: Mapped[Any] = mapped_column(JSONB)
    omitted_vs_others: Mapped[Any] = mapped_column(JSONB)
    model: Mapped[str] = mapped_column(Text)
    prompt_version: Mapped[str] = mapped_column(Text)
    schema_version: Mapped[str] = mapped_column(Text)


class FactCheck(Base):
    __tablename__ = "fact_checks"

    id: Mapped[uuid.UUID] = _pk()
    source_id: Mapped[uuid.UUID] = _fk("sources.id")
    url: Mapped[str] = mapped_column(Text, unique=True)
    claim_reviewed: Mapped[str] = mapped_column(Text)
    rating_original: Mapped[str | None] = mapped_column(Text)
    rating_normalized: Mapped[str | None] = mapped_column(Text)
    published_at: Mapped[datetime | None] = mapped_column(TSTZ)
    language: Mapped[str | None] = mapped_column(Text)


class ClaimFactCheckMatch(Base):
    __tablename__ = "claim_fact_check_matches"

    claim_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("claims.id", ondelete="CASCADE"), primary_key=True
    )
    fact_check_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("fact_checks.id", ondelete="CASCADE"), primary_key=True
    )
    similarity: Mapped[float] = mapped_column(REAL)
    verdict: Mapped[str] = mapped_column(Text)
    verified_by_llm: Mapped[bool] = mapped_column(Boolean)
    rationale: Mapped[str | None] = mapped_column(Text)
    schema_version: Mapped[str | None] = mapped_column(Text)
    prompt_version: Mapped[str | None] = mapped_column(Text)


class StorySummary(Base):
    __tablename__ = "story_summaries"
    __table_args__ = (
        UniqueConstraint("story_id", "version", "lang"),
        Index("ix_story_summaries_story_state", "story_id", "state", text("version DESC")),
    )

    id: Mapped[uuid.UUID] = _pk()
    story_id: Mapped[uuid.UUID] = _fk("stories.id", ondelete="CASCADE")
    version: Mapped[int] = mapped_column(Integer)
    lang: Mapped[str] = mapped_column(Text)
    summary: Mapped[Any] = mapped_column(JSONB)
    agreements: Mapped[Any] = mapped_column(JSONB)
    disagreements: Mapped[Any] = mapped_column(JSONB)
    model: Mapped[str] = mapped_column(Text)
    prompt_version: Mapped[str] = mapped_column(Text)
    verifier_result: Mapped[Any] = mapped_column(JSONB)
    created_at: Mapped[datetime] = _now()
    framing: Mapped[Any | None] = mapped_column(JSONB)
    state: Mapped[str] = mapped_column(Text, server_default="published")  # published | review | failed
    source_count: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    schema_version: Mapped[str] = mapped_column(Text, server_default="1.0")


# ---------------------------------------------------------------- users, memory, logs


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = _pk()
    created_at: Mapped[datetime] = _now()
    consent_at: Mapped[datetime | None] = mapped_column(TSTZ)


class UserPreference(Base):
    __tablename__ = "user_preferences"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    key: Mapped[str] = mapped_column(Text, primary_key=True)
    value: Mapped[Any] = mapped_column(JSONB)
    updated_at: Mapped[datetime] = _now()


class StoryView(Base):
    """Episodic memory. The reference DDL has no primary key; a surrogate `id` is added
    because the ORM requires one (docs/DECISIONS.md, ADR-0004)."""

    __tablename__ = "story_views"

    id: Mapped[uuid.UUID] = _pk()
    user_id: Mapped[uuid.UUID] = _fk("users.id", ondelete="CASCADE")
    story_id: Mapped[uuid.UUID] = _fk("stories.id", ondelete="CASCADE")
    viewed_at: Mapped[datetime] = _now()
    story_version_seen: Mapped[int | None] = mapped_column(Integer)


class AskTurn(Base):
    __tablename__ = "ask_turns"
    __table_args__ = (Index("ix_ask_turns_created_at", "created_at"),)  # retention purge

    id: Mapped[uuid.UUID] = _pk()
    session_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    user_id: Mapped[uuid.UUID | None] = _fk("users.id", ondelete="SET NULL", nullable=True)
    raw_query: Mapped[str] = mapped_column(Text)
    neutral_query: Mapped[str | None] = mapped_column(Text)
    lang: Mapped[str | None] = mapped_column(Text)
    intent: Mapped[str | None] = mapped_column(Text)
    story_ids: Mapped[list[uuid.UUID] | None] = mapped_column(ARRAY(UUID(as_uuid=True)))
    answer: Mapped[Any | None] = mapped_column(JSONB)
    abstained: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    model_versions: Mapped[Any | None] = mapped_column(JSONB)
    prompt_versions: Mapped[Any | None] = mapped_column(JSONB)
    langsmith_run_id: Mapped[str | None] = mapped_column(Text)
    # G-OPS-04 audit trail (ADR-0033): what was retrieved, how it was judged, how it ended.
    outcome: Mapped[str | None] = mapped_column(Text)  # answer | fallback | abstain | error
    abstain_reason: Mapped[str | None] = mapped_column(Text)
    evidence_article_ids: Mapped[list[str] | None] = mapped_column(ARRAY(Text))
    verifier: Mapped[Any | None] = mapped_column(JSONB)
    errors: Mapped[Any | None] = mapped_column(JSONB)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = _now()


class GuardEvent(Base):
    __tablename__ = "guard_events"
    __table_args__ = (Index("ix_guard_events_guard_id_created_at", "guard_id", text("created_at DESC")),)

    id: Mapped[uuid.UUID] = _pk()
    run_id: Mapped[str] = mapped_column(Text)
    guard_id: Mapped[str] = mapped_column(Text)
    stage: Mapped[str] = mapped_column(Text)
    passed: Mapped[bool] = mapped_column(Boolean)
    action: Mapped[str] = mapped_column(Text)
    reason: Mapped[str | None] = mapped_column(Text)
    score: Mapped[float | None] = mapped_column(REAL)
    meta: Mapped[Any | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = _now()


class ReviewQueueItem(Base):
    __tablename__ = "review_queue"

    id: Mapped[uuid.UUID] = _pk()
    kind: Mapped[str] = mapped_column(Text)
    ref_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    reason: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, server_default="open")
    assigned_to: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = _now()
    resolved_at: Mapped[datetime | None] = mapped_column(TSTZ)


class Feedback(Base):
    __tablename__ = "feedback"

    id: Mapped[uuid.UUID] = _pk()
    kind: Mapped[str] = mapped_column(Text)
    ref_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = _now()


class DeadLetter(Base):
    __tablename__ = "dead_letters"

    id: Mapped[uuid.UUID] = _pk()
    stage: Mapped[str] = mapped_column(Text)
    payload: Mapped[Any] = mapped_column(JSONB)
    error: Mapped[str] = mapped_column(Text)
    attempts: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    created_at: Mapped[datetime] = _now()
