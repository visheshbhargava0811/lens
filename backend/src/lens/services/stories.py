"""Read services for the public API (docs/09). Routers call these; these query Postgres.

Every figure comes from `story_stats` (pure code in lens.stats) or from provenance-backed source
rows. Nothing here infers a stance or a rating. Killed or held stories are never served.
"""

from __future__ import annotations

import base64
import binascii
import uuid
from collections import defaultdict
from datetime import datetime
from typing import Any, Literal

from sqlalchemy import Select, and_, func, or_, select
from sqlalchemy.orm import Session

from lens.core.config_files import load_yaml
from lens.db.models import (
    AnalysisDepth,
    Article,
    Framing,
    Source,
    SourceOwnership,
    SourceRating,
    Story,
    StoryArticle,
    StoryStats,
)
from lens.schemas import api
from lens.stats.coverage import STANCE_BUCKETS, factuality_confidence, percentages

M_STANCE = "/methodology#stance"
M_FACTUALITY = "/methodology#factuality"
M_OWNERSHIP = "/methodology#ownership"
M_BLINDSPOTS = "/methodology#blindspots"
M_SOURCES = "/methodology#sources"


def _cfg() -> dict[str, Any]:
    return load_yaml("guardrails.yaml")


def _visible() -> Any:
    return and_(Story.kill_switch.is_(False), Story.review_status != "held")


# ---------------------------------------------------------------- cards


def _card(story: Story, stats: StoryStats | None, g: dict[str, Any]) -> api.StoryCard:
    n = story.source_count
    blind: api.StanceBlindspot | api.LanguageBlindspot | None = None
    if stats is None:  # stats not computed yet: everything unclassified and unrated
        stance = {**{b: 0 for b in STANCE_BUCKETS}, "unclassified": n}
        fact = {"high": 0, "mixed": 0, "low": 0, "unrated": n}
        conf: api.Confidence = "low"
        by_lang: dict[str, int] = {}
    else:
        stance, fact, conf = stats.stance_counts, stats.factuality_counts, stats.coverage_confidence.value
        by_lang = stats.language_counts
        if stats.blindspot_type == "stance" and stats.blindspot_skew in STANCE_BUCKETS:
            blind = api.StanceBlindspot(skew=stats.blindspot_skew, score=stats.blindspot_score or 0)
        elif stats.blindspot_type == "language":
            blind = api.LanguageBlindspot(skew=stats.blindspot_skew or "", score=stats.blindspot_score or 0)

    coverage: api.CoverageAvailable | api.CoverageLimited
    if n < g["min_sources_for_bar"]:
        coverage = api.CoverageLimited(min_sources=g["min_sources_for_bar"], confidence=conf, methodology_url=M_STANCE)
    else:
        keys = [*STANCE_BUCKETS, "unclassified"]
        values = [int(stance.get(k, 0)) for k in keys]
        pcts = percentages(values)
        coverage = api.CoverageAvailable(
            buckets=[
                api.CoverageBucket(key=k, sources=v, pct=p)
                for k, v, p in zip(STANCE_BUCKETS, values, pcts, strict=False)
            ],
            unclassified=api.SourcesPct(sources=values[-1], pct=pcts[-1]),
            confidence=conf,
            methodology_url=M_STANCE,
        )

    return api.StoryCard(
        id=str(story.id),
        slug=story.slug,
        headline=story.headline,
        headline_lang=story.headline_lang,
        status=story.status.value,
        updated_at=story.last_updated_at,
        topic=story.topic,
        image=None,  # no source has image_policy=hotlink; images are never stored (docs/01)
        counts=api.Counts(sources=n, articles=story.article_count, by_language=by_lang),
        coverage=coverage,
        factuality=api.FactualityCounts(
            high=fact.get("high", 0),
            mixed=fact.get("mixed", 0),
            low=fact.get("low", 0),
            unrated=fact.get("unrated", 0),
            confidence=factuality_confidence(fact, g["stats"]["factuality_confidence"]),
            methodology_url=M_FACTUALITY,
        ),
        blindspot=blind,
        summary_preview=None,  # summaries arrive in Phase 4
    )


def _cards(session: Session, q: Select[Any]) -> list[api.StoryCard]:
    g = _cfg()
    rows = session.execute(q.outerjoin(StoryStats, StoryStats.story_id == Story.id).add_columns(StoryStats)).all()
    return [_card(r[0], r[1], g) for r in rows]


# ---------------------------------------------------------------- feed


def _encode_cursor(ts: datetime, sid: uuid.UUID) -> str:
    return base64.urlsafe_b64encode(f"{ts.isoformat()}|{sid}".encode()).decode()


def _decode_cursor(cursor: str) -> tuple[datetime, uuid.UUID]:
    try:
        ts, sid = base64.urlsafe_b64decode(cursor.encode()).decode().split("|")
        return datetime.fromisoformat(ts), uuid.UUID(sid)
    except (ValueError, binascii.Error) as e:
        raise ValueError("invalid cursor") from e


def feed(
    session: Session,
    tab: Literal["home", "blindspot", "local"] = "home",
    topic: str | None = None,
    state: str | None = None,
    cursor: str | None = None,
    limit: int = 20,
) -> api.StoryCardPage:
    g = _cfg()
    q = select(Story).where(_visible(), Story.source_count >= g["feed_min_sources"])
    if topic and topic != "top":
        q = q.where(Story.topic == topic)
    if tab == "blindspot":
        q = q.where(Story.id.in_(select(StoryStats.story_id).where(StoryStats.blindspot_type.is_not(None))))
    elif tab == "local":
        q = q.where(Story.region == state) if state else q.where(Story.region.is_not(None))
    if cursor:
        ts, sid = _decode_cursor(cursor)
        q = q.where(or_(Story.last_updated_at < ts, and_(Story.last_updated_at == ts, Story.id < sid)))
    q = q.order_by(Story.last_updated_at.desc(), Story.id.desc()).limit(limit + 1)
    items = _cards(session, q)
    more = len(items) > limit
    items = items[:limit]
    nxt = _encode_cursor(items[-1].updated_at, uuid.UUID(items[-1].id)) if more and items else None
    return api.StoryCardPage(items=items, next_cursor=nxt)


def blindspots(session: Session, kind: Literal["stance", "language"], limit: int = 50) -> api.Blindspots:
    g = _cfg()
    q = (
        select(Story)
        .where(
            _visible(),
            Story.source_count >= g["feed_min_sources"],
            Story.id.in_(select(StoryStats.story_id).where(StoryStats.blindspot_type == kind)),
        )
        .order_by(Story.last_updated_at.desc())
        .limit(limit)
    )
    return api.Blindspots(type=kind, items=_cards(session, q), methodology_url=M_BLINDSPOTS)


def topics(session: Session) -> api.Topics:
    rows = session.execute(
        select(Story.topic)
        .where(_visible(), Story.topic.is_not(None))
        .group_by(Story.topic)
        .order_by(func.count().desc())
    ).scalars()
    return api.Topics(items=[api.Topic(slug=t, name=t) for t in rows if t])


# ---------------------------------------------------------------- story


def find_story(session: Session, id_or_slug: str) -> Story | None:
    try:
        cond = Story.id == uuid.UUID(id_or_slug)
    except ValueError:
        cond = Story.slug == id_or_slug
    return session.execute(select(Story).where(cond, _visible())).scalar_one_or_none()


def story_detail(session: Session, story: Story) -> api.StoryDetail:
    card = _cards(session, select(Story).where(Story.id == story.id))[0]
    stats = session.get(StoryStats, story.id)
    owners = stats.ownership_counts if stats else {}
    unknown = owners.get("unknown", 0) if stats else story.source_count
    partial = session.execute(
        select(func.count(func.distinct(Article.source_id)))
        .join(StoryArticle, StoryArticle.article_id == Article.id)
        .where(StoryArticle.story_id == story.id, Article.analysis_depth != AnalysisDepth.full_text)
    ).scalar_one()
    limitations: list[str] = []
    if partial:
        limitations.append(f"Based on headlines and summaries for {partial} of {story.source_count} sources.")
    if stats is None or stats.stance_counts.get("unclassified", 0) >= story.source_count:
        limitations.append("Stance has not been classified for this story yet.")
    if card.factuality.unrated:
        limitations.append(f"{card.factuality.unrated} of {story.source_count} sources have no factuality rating.")
    return api.StoryDetail(
        story=card,
        summary=None,  # Phase 4
        framing_differences=[],  # Phase 4
        fact_checks=[],  # Phase 5
        ownership=api.Ownership(
            groups=[api.OwnershipGroup(name=k, sources=v) for k, v in sorted(owners.items()) if k != "unknown"],
            unknown=unknown,
            methodology_url=M_OWNERSHIP,
        ),
        limitations=limitations,
    )


def _best_ratings(session: Session, source_ids: list[uuid.UUID]) -> dict[uuid.UUID, SourceRating]:
    order = {"low": 0, "medium": 1, "high": 2}
    best: dict[uuid.UUID, SourceRating] = {}
    for r in session.execute(
        select(SourceRating).where(SourceRating.dimension == "factuality", SourceRating.source_id.in_(source_ids))
    ).scalars():
        cur = best.get(r.source_id)
        if cur is None or (order[r.confidence], r.retrieved_at) > (order[cur.confidence], cur.retrieved_at):
            best[r.source_id] = r
    return best


def _latest_owners(session: Session, source_ids: list[uuid.UUID]) -> dict[uuid.UUID, SourceOwnership]:
    out: dict[uuid.UUID, SourceOwnership] = {}
    for o in session.execute(select(SourceOwnership).where(SourceOwnership.source_id.in_(source_ids))).scalars():
        if o.source_id not in out or o.retrieved_at > out[o.source_id].retrieved_at:
            out[o.source_id] = o
    return out


def story_articles(
    session: Session, story: Story, stance: str | None = None, lang: str | None = None
) -> api.StoryArticles:
    rows = session.execute(
        select(Article, Source, Framing)
        .join(StoryArticle, StoryArticle.article_id == Article.id)
        .join(Source, Source.id == Article.source_id)
        .outerjoin(Framing, and_(Framing.article_id == Article.id, Framing.story_id == story.id))
        .where(StoryArticle.story_id == story.id)
        .order_by(Article.published_at.desc())
    ).all()
    src_ids = list({s.id for _, s, _ in rows})
    ratings, owners = _best_ratings(session, src_ids), _latest_owners(session, src_ids)
    carried: dict[uuid.UUID, list[str]] = defaultdict(list)
    for a, s, _ in rows:
        if a.original_article_id is not None:
            carried[a.original_article_id].append(s.name)

    items: list[api.ArticleRow] = []
    for a, s, f in rows:
        st = api.ArticleStance(
            value=f.stance.value if f else "unclassified",
            target=f.stance_target.value if f else "none",
            confidence=f.stance_confidence.value if f else "low",
        )
        if stance and st.value != stance:
            continue
        if lang and a.language.split("-")[0] != lang:
            continue
        r, o = ratings.get(s.id), owners.get(s.id)
        items.append(
            api.ArticleRow(
                id=str(a.id),
                source=api.ArticleSource(id=str(s.id), name=s.name, logo_url=None, language=a.language),
                headline=a.title,
                headline_lang=a.language,
                published_at=a.published_at,
                url=a.url,
                stance=st,
                analysis_depth=a.analysis_depth.value,
                source_factuality=api.SourceFactuality(
                    rater=r.rater, value=r.value, method_url=r.method_url, confidence=r.confidence.value
                )
                if r
                else None,
                source_ownership=api.SourceOwnershipRef(owner=o.owner_name, evidence_url=o.evidence_url) if o else None,
                is_syndicated=a.is_syndicated,
                also_carried_by=sorted(set(carried.get(a.id, []))),
            )
        )
    return api.StoryArticles(items=items, methodology_url=M_STANCE)


# ---------------------------------------------------------------- sources and methodology


def _source_summary(s: Source) -> api.SourceSummary:
    return api.SourceSummary(
        id=str(s.id),
        slug=s.slug,
        name=s.name,
        homepage_url=s.homepage_url,
        languages=list(s.language_codes),
        region=s.region,
        is_wire=s.is_wire,
        license_mode=s.license_mode.value,
    )


def sources(session: Session) -> api.SourceList:
    rows = session.execute(select(Source).where(Source.active).order_by(Source.name)).scalars()
    return api.SourceList(items=[_source_summary(s) for s in rows])


def find_source(session: Session, id_or_slug: str) -> Source | None:
    try:
        cond = Source.id == uuid.UUID(id_or_slug)
    except ValueError:
        cond = Source.slug == id_or_slug
    return session.execute(select(Source).where(cond)).scalar_one_or_none()


def source_detail(session: Session, s: Source, recent: int = 10) -> api.SourceDetail:
    owners = session.execute(
        select(SourceOwnership).where(SourceOwnership.source_id == s.id).order_by(SourceOwnership.retrieved_at.desc())
    ).scalars()
    ratings = session.execute(
        select(SourceRating).where(SourceRating.source_id == s.id).order_by(SourceRating.retrieved_at.desc())
    ).scalars()
    in_source = select(StoryArticle.story_id).join(Article, Article.id == StoryArticle.article_id)
    q = (
        select(Story)
        .where(_visible(), Story.id.in_(in_source.where(Article.source_id == s.id)))
        .order_by(Story.last_updated_at.desc())
        .limit(recent)
    )
    return api.SourceDetail(
        source=_source_summary(s),
        ownership=[
            api.OwnershipRecord(
                owner_name=o.owner_name,
                owner_type=o.owner_type,
                parent_group=o.parent_group,
                evidence_url=o.evidence_url,
                retrieved_at=o.retrieved_at,
                confidence=o.confidence.value,
            )
            for o in owners
        ],
        ratings=[
            api.RatingRecord(
                dimension=r.dimension,
                rater=r.rater,
                value=r.value,
                method_url=r.method_url,
                evidence_url=r.evidence_url,
                retrieved_at=r.retrieved_at,
                confidence=r.confidence.value,
            )
            for r in ratings
        ],
        recent_stories=_cards(session, q),
        methodology_url=M_SOURCES,
    )


def methodology(session: Session) -> api.Methodology:
    g = _cfg()
    raters = session.execute(
        select(
            SourceRating.rater,
            SourceRating.dimension,
            SourceRating.method_url,
            func.count(func.distinct(SourceRating.source_id)),
        )
        .group_by(SourceRating.rater, SourceRating.dimension, SourceRating.method_url)
        .order_by(SourceRating.rater)
    ).all()
    return api.Methodology(
        min_sources_for_bar=g["min_sources_for_bar"],
        min_sources_for_blindspot=g["min_sources_for_blindspot"],
        blindspot_stance_share=g["stats"]["blindspot_stance_share"],
        blindspot_language_share=g["stats"]["blindspot_language_share"],
        feed_min_sources=g["feed_min_sources"],
        raters=[api.Rater(rater=r, dimension=d, method_url=m, sources_rated=n) for r, d, m, n in raters],
    )
