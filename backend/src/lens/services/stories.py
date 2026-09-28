"""Read services for the public API (docs/09). Routers call these; these query Postgres.

Every figure comes from `story_stats` (pure code in lens.stats) or from provenance-backed source
rows. Nothing here infers a bias label or a rating. Killed or held stories are never served.
"""

from __future__ import annotations

import base64
import binascii
import re
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
    Chunk,
    Claim,
    ClaimFactCheckMatch,
    FactCheck,
    ImagePolicy,
    Source,
    SourceOwnership,
    SourceRating,
    Story,
    StoryArticle,
    StoryStats,
    StorySummary,
)
from lens.pipeline.stats import best_ratings
from lens.schemas import api
from lens.stats.coverage import BIAS_BUCKETS, bucket, percentages, rated_share_confidence

M_BIAS = "/methodology#bias"
M_FACTUALITY = "/methodology#factuality"
M_OWNERSHIP = "/methodology#ownership"
M_BLINDSPOTS = "/methodology#blindspots"
M_SOURCES = "/methodology#sources"


def _cfg() -> dict[str, Any]:
    return load_yaml("guardrails.yaml")


def visible_story() -> Any:
    return and_(Story.kill_switch.is_(False), Story.review_status != "held")


# ---------------------------------------------------------------- cards


def coverage_bar(
    bias: dict[str, int], n_sources: int, conf: api.Confidence, g: dict[str, Any]
) -> api.CoverageAvailable | api.CoverageLimited:
    """Outlet Left/Center/Right bar from distinct-source counts; limited below `min_sources_for_bar`."""
    if n_sources < g["min_sources_for_bar"]:
        return api.CoverageLimited(min_sources=g["min_sources_for_bar"], confidence=conf, methodology_url=M_BIAS)
    keys = [*BIAS_BUCKETS, "unrated"]
    values = [int(bias.get(k, 0)) for k in keys]
    pcts = percentages(values)
    return api.CoverageAvailable(
        buckets=[
            api.CoverageBucket(key=k, sources=v, pct=p) for k, v, p in zip(BIAS_BUCKETS, values, pcts, strict=False)
        ],
        unrated=api.SourcesPct(sources=values[-1], pct=pcts[-1]),
        confidence=conf,
        methodology_url=M_BIAS,
    )


def _card(story: Story, stats: StoryStats | None, g: dict[str, Any], preview: str | None = None) -> api.StoryCard:
    n = story.source_count
    blind: api.BiasBlindspot | api.LanguageBlindspot | None = None
    if stats is None:  # stats not computed yet: everything unrated
        bias = {**{b: 0 for b in BIAS_BUCKETS}, "unrated": n}
        fact = {"high": 0, "mixed": 0, "low": 0, "unrated": n}
        conf: api.Confidence = "low"
        by_lang: dict[str, int] = {}
    else:
        bias, fact, conf = stats.bias_counts, stats.factuality_counts, stats.coverage_confidence.value
        by_lang = stats.language_counts
        if stats.blindspot_type == "bias" and stats.blindspot_skew in BIAS_BUCKETS:
            blind = api.BiasBlindspot(skew=stats.blindspot_skew, score=stats.blindspot_score or 0)
        elif stats.blindspot_type == "language":
            blind = api.LanguageBlindspot(skew=stats.blindspot_skew or "", score=stats.blindspot_score or 0)

    coverage = coverage_bar(bias, n, conf, g)

    return api.StoryCard(
        id=str(story.id),
        slug=story.slug,
        headline=story.headline,
        headline_lang=story.headline_lang,
        status=story.status.value,
        updated_at=story.last_updated_at,
        topic=story.topic,
        image=None,  # set by story_cards from hotlink sources (story_images)
        counts=api.Counts(sources=n, articles=story.article_count, by_language=by_lang),
        coverage=coverage,
        factuality=api.FactualityCounts(
            high=fact.get("high", 0),
            mixed=fact.get("mixed", 0),
            low=fact.get("low", 0),
            unrated=fact.get("unrated", 0),
            confidence=rated_share_confidence(fact, g["stats"]["rated_share_confidence"]),
            methodology_url=M_FACTUALITY,
        ),
        blindspot=blind,
        summary_preview=preview,
    )


def story_cards(session: Session, q: Select[Any]) -> list[api.StoryCard]:
    g = _cfg()
    rows = session.execute(q.outerjoin(StoryStats, StoryStats.story_id == Story.id).add_columns(StoryStats)).all()
    ids = [r[0].id for r in rows]
    latest, images = latest_published(session, ids), story_images(session, ids)
    cards = [_card(r[0], r[1], g, _preview(latest.get(r[0].id))) for r in rows]
    for c in cards:
        c.image = images.get(c.id)
    return cards


def story_images(session: Session, story_ids: list[uuid.UUID]) -> dict[str, api.StoryImage]:
    """Newest article image per story, only from sources whose image_policy is hotlink (docs/09, ADR-0034).
    The URL points at the outlet's own server: never fetched, cached or re-hosted by Lens."""
    if not story_ids:
        return {}
    rows = session.execute(
        select(StoryArticle.story_id, Article.image_url, Source.name)
        .join(Article, Article.id == StoryArticle.article_id)
        .join(Source, Source.id == Article.source_id)
        .where(
            StoryArticle.story_id.in_(story_ids),
            Article.image_url.is_not(None),
            Source.image_policy == ImagePolicy.hotlink,
        )
        .order_by(StoryArticle.story_id, Article.published_at.desc())
        .distinct(StoryArticle.story_id)
    ).all()
    return {str(sid): api.StoryImage(url=url, source_name=name) for sid, url, name in rows}


def latest_published(session: Session, story_ids: list[uuid.UUID]) -> dict[uuid.UUID, StorySummary]:
    """Newest published summary per story. Held (review) and failed versions are never served."""
    if not story_ids:
        return {}
    rows = session.execute(
        select(StorySummary)
        .where(StorySummary.story_id.in_(story_ids), StorySummary.state == "published")
        .order_by(StorySummary.story_id, StorySummary.version.desc())
        .distinct(StorySummary.story_id)
    ).scalars()
    return {r.story_id: r for r in rows}


def _preview(row: StorySummary | None) -> str | None:
    if row is None or not row.summary:
        return None
    names = {c["ref"]: c["source_name"] for s in row.summary for c in s["citations"] if "ref" in c}
    return _unmask(row.summary[0]["text"], names)


_REF_GROUP = re.compile(r"\s*\((?:A\d+(?:\s*(?:,|and|&)\s*)?)+\)")
_REF = re.compile(r"\bA(\d+)\b")


def _unmask(text: str, names: dict[str, str]) -> str:
    """The model cites masked refs (A1..An). Readers get outlet names, re-attached in code (docs/06):
    parenthetical ref lists are dropped (citations are shown as chips) and remaining refs become names."""
    text = _REF_GROUP.sub("", text)
    return _REF.sub(lambda m: names.get(f"A{m.group(1)}", m.group(0)), text).strip()


def cited_api(sections: list[list[dict[str, Any]]], chunk_of: dict[str, str]) -> list[list[api.CitedSentence]]:
    """Stored sentences -> API shape, numbering citations continuously across all sections."""
    names = {
        c["ref"]: c["source_name"] for sentences in sections for s in sentences for c in s["citations"] if "ref" in c
    }
    n = 0
    out: list[list[api.CitedSentence]] = []
    for sentences in sections:
        section = []
        for s in sentences:
            cites = []
            for c in s["citations"]:
                n += 1
                cites.append(
                    api.Citation(
                        n=n,
                        article_id=c["article_id"],
                        source_name=c["source_name"],
                        chunk_id=chunk_of.get(c["article_id"], ""),
                    )
                )
            section.append(api.CitedSentence(text=_unmask(s["text"], names), citations=cites))
        out.append(section)
    return out


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
    topics: list[str] | None = None,
) -> api.StoryCardPage:
    """`topics` (For you, docs/11): which stories are listed, never which outlets a story shows."""
    g = _cfg()
    q = select(Story).where(visible_story(), Story.source_count >= g["feed_min_sources"])
    if topic and topic != "top":
        q = q.where(Story.topic == topic)
    if topics is not None:
        q = q.where(Story.topic.in_(topics))
    if tab == "blindspot":
        q = q.where(Story.id.in_(select(StoryStats.story_id).where(StoryStats.blindspot_type.is_not(None))))
    elif tab == "local":
        q = q.where(Story.region == state) if state else q.where(Story.region.is_not(None))
    if cursor:
        ts, sid = _decode_cursor(cursor)
        q = q.where(or_(Story.last_updated_at < ts, and_(Story.last_updated_at == ts, Story.id < sid)))
    q = q.order_by(Story.last_updated_at.desc(), Story.id.desc()).limit(limit + 1)
    items = story_cards(session, q)
    more = len(items) > limit
    items = items[:limit]
    nxt = _encode_cursor(items[-1].updated_at, uuid.UUID(items[-1].id)) if more and items else None
    return api.StoryCardPage(items=items, next_cursor=nxt)


def blindspots(session: Session, kind: Literal["bias", "language"], limit: int = 50) -> api.Blindspots:
    g = _cfg()
    q = (
        select(Story)
        .where(
            visible_story(),
            Story.source_count >= g["feed_min_sources"],
            Story.id.in_(select(StoryStats.story_id).where(StoryStats.blindspot_type == kind)),
        )
        .order_by(Story.last_updated_at.desc())
        .limit(limit)
    )
    return api.Blindspots(type=kind, items=story_cards(session, q), methodology_url=M_BLINDSPOTS)


def topics(session: Session) -> api.Topics:
    rows = session.execute(
        select(Story.topic)
        .where(visible_story(), Story.topic.is_not(None))
        .group_by(Story.topic)
        .order_by(func.count().desc())
    ).scalars()
    return api.Topics(items=[api.Topic(slug=t, name=t) for t in rows if t])


# ---------------------------------------------------------------- story


def story_fact_checks(session: Session, story_ids: list[uuid.UUID], limit: int = 8) -> list[api.FactCheckRef]:
    """Fact-checks matched (LLM-verified) to claims in these stories' articles; same_claim first (docs/04 s9)."""
    rows = session.execute(
        select(FactCheck, Source.name, ClaimFactCheckMatch.verdict)
        .join(ClaimFactCheckMatch, ClaimFactCheckMatch.fact_check_id == FactCheck.id)
        .join(Claim, Claim.id == ClaimFactCheckMatch.claim_id)
        .join(StoryArticle, StoryArticle.article_id == Claim.article_id)
        .join(Source, Source.id == FactCheck.source_id)
        .where(StoryArticle.story_id.in_(story_ids))
    ).all()
    best: dict[uuid.UUID, tuple[FactCheck, str, str]] = {}
    for fc, name, verdict in rows:
        if fc.id not in best or verdict == "same_claim":
            best[fc.id] = (fc, name, verdict)
    ordered = sorted(
        best.values(),
        key=lambda r: (r[2] != "same_claim", -(r[0].published_at.timestamp() if r[0].published_at else 0)),
    )
    return [fact_check_ref(fc, name, verdict) for fc, name, verdict in ordered[:limit]]


def fact_check_ref(fc: FactCheck, fact_checker: str, verdict: str) -> api.FactCheckRef:
    return api.FactCheckRef(
        claim=fc.claim_reviewed,
        fact_checker=fact_checker,
        rating=fc.rating_original or fc.rating_normalized or "other",
        rating_normalized=fc.rating_normalized or "other",
        match=verdict,
        url=fc.url,
        published_at=fc.published_at,
    )


def find_story(session: Session, id_or_slug: str) -> Story | None:
    try:
        cond = Story.id == uuid.UUID(id_or_slug)
    except ValueError:
        cond = Story.slug == id_or_slug
    return session.execute(select(Story).where(cond, visible_story())).scalar_one_or_none()


def story_detail(session: Session, story: Story) -> api.StoryDetail:
    card = story_cards(session, select(Story).where(Story.id == story.id))[0]
    stats = session.get(StoryStats, story.id)
    owners = stats.ownership_counts if stats else {}
    unknown = owners.get("unknown", 0) if stats else story.source_count
    partial = session.execute(
        select(func.count(func.distinct(Article.source_id)))
        .join(StoryArticle, StoryArticle.article_id == Article.id)
        .where(StoryArticle.story_id == story.id, Article.analysis_depth != AnalysisDepth.full_text)
    ).scalar_one()
    row = latest_published(session, [story.id]).get(story.id)
    summary: api.StorySummary | None = None
    framing: list[api.CitedSentence] = []
    if row is not None:
        ids = {
            c["article_id"]
            for section in (row.summary, row.agreements, row.disagreements, *(row.framing or {}).values())
            for s in section
            for c in s["citations"]
        }
        chunk_of = {
            str(a): str(c)
            for a, c in session.execute(
                select(Chunk.article_id, Chunk.id).where(
                    Chunk.article_id.in_([uuid.UUID(i) for i in ids]), Chunk.idx == 0
                )
            ).all()
        }
        f = row.framing or {}
        sents, agree, disagree, diffs, only = cited_api(
            [row.summary, row.agreements, row.disagreements, f.get("differences", []), f.get("only_in_some", [])],
            chunk_of,
        )
        summary = api.StorySummary(
            lang=row.lang,
            version=row.version,
            generated_at=row.created_at,
            # Only published rows are served, and publishing requires a judge verdict: every shown
            # sentence passed it (flagged ones were pruned, see story_graph).
            verified=(row.verifier_result or {}).get("verdict") is not None,
            sentences=sents,
            agreements=agree,
            disagreements=disagree,
        )
        framing = diffs + only
    limitations: list[str] = []
    if partial:
        # Syndicated copies make distinct source ids exceed the deduplicated source count; cap it.
        shown = min(partial, story.source_count)
        limitations.append(f"Based on headlines and summaries for {shown} of {story.source_count} sources.")
    if card.coverage.available and card.coverage.unrated.sources:
        limitations.append(f"{card.coverage.unrated.sources} of {story.source_count} sources have no bias rating.")
    if card.factuality.unrated:
        limitations.append(f"{card.factuality.unrated} of {story.source_count} sources have no factuality rating.")
    return api.StoryDetail(
        story=card,
        summary=summary,
        framing_differences=framing,
        fact_checks=story_fact_checks(session, [story.id]),
        ownership=api.Ownership(
            groups=[api.OwnershipGroup(name=k, sources=v) for k, v in sorted(owners.items()) if k != "unknown"],
            unknown=unknown,
            methodology_url=M_OWNERSHIP,
        ),
        limitations=limitations,
    )


def _latest_owners(session: Session, source_ids: list[uuid.UUID]) -> dict[uuid.UUID, SourceOwnership]:
    out: dict[uuid.UUID, SourceOwnership] = {}
    for o in session.execute(select(SourceOwnership).where(SourceOwnership.source_id.in_(source_ids))).scalars():
        if o.source_id not in out or o.retrieved_at > out[o.source_id].retrieved_at:
            out[o.source_id] = o
    return out


def _rating_ref(r: SourceRating | None) -> api.RatingRef | None:
    if r is None:
        return None
    return api.RatingRef(rater=r.rater, value=r.value, method_url=r.method_url, confidence=r.confidence.value)


def story_articles(
    session: Session, story: Story, bias: str | None = None, lang: str | None = None
) -> api.StoryArticles:
    """Articles with their outlet's bias and factuality rating (as the rater worded it) and owner.
    `bias` filters by bucket (left | center | right | unrated), mapped exactly as in the stats."""
    rows = session.execute(
        select(Article, Source)
        .join(StoryArticle, StoryArticle.article_id == Article.id)
        .join(Source, Source.id == Article.source_id)
        .where(StoryArticle.story_id == story.id)
        .order_by(Article.published_at.desc())
    ).all()
    src_ids = list({s.id for _, s in rows})
    biases, facts = best_ratings(session, "bias", src_ids), best_ratings(session, "factuality", src_ids)
    owners = _latest_owners(session, src_ids)
    value_map = _cfg()["stats"]["bias_value_map"]
    carried: dict[uuid.UUID, list[str]] = defaultdict(list)
    for a, s in rows:
        if a.original_article_id is not None:
            carried[a.original_article_id].append(s.name)

    items: list[api.ArticleRow] = []
    for a, s in rows:
        b = biases.get(s.id)
        b_bucket = bucket(b.value if b else None, value_map, BIAS_BUCKETS)
        if bias and b_bucket != bias:
            continue
        if lang and a.language.split("-")[0] != lang:
            continue
        o = owners.get(s.id)
        items.append(
            api.ArticleRow(
                id=str(a.id),
                source=api.ArticleSource(id=str(s.id), name=s.name, logo_url=None, language=a.language),
                headline=a.title,
                headline_lang=a.language,
                published_at=a.published_at,
                url=a.url,
                analysis_depth=a.analysis_depth.value,
                bias=b_bucket,
                source_bias=_rating_ref(b),
                source_factuality=_rating_ref(facts.get(s.id)),
                source_ownership=api.SourceOwnershipRef(owner=o.owner_name, evidence_url=o.evidence_url) if o else None,
                is_syndicated=a.is_syndicated,
                also_carried_by=sorted(set(carried.get(a.id, []))),
            )
        )
    return api.StoryArticles(items=items, methodology_url=M_BIAS)


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
        .where(visible_story(), Story.id.in_(in_source.where(Article.source_id == s.id)))
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
        recent_stories=story_cards(session, q),
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
        blindspot_bias_share=g["stats"]["blindspot_bias_share"],
        blindspot_language_share=g["stats"]["blindspot_language_share"],
        feed_min_sources=g["feed_min_sources"],
        raters=[api.Rater(rater=r, dimension=d, method_url=m, sources_rated=n) for r, d, m, n in raters],
    )
