"""Stats node (Graph 1, node 11): compute story_stats for stories whose articles changed.

Stance comes from `framings` (Phase 4). Until then every source is unclassified, which the
math turns into low confidence and no stance blindspot. Source facts come only from imported,
provenance-backed rows (rule 7); anything missing is unrated / unknown.
"""

from __future__ import annotations

import sys
import uuid
from collections import defaultdict
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from lens.core.config_files import load_yaml
from lens.core.logging import configure_logging, get_logger
from lens.db.models import Article, Framing, SourceOwnership, SourceRating, StoryArticle, StoryStats
from lens.db.session import get_engine
from lens.stats.coverage import ArticleFacts, SourceFacts, compute_story_stats

log = get_logger(__name__)
_CONF_ORDER = {"low": 0, "medium": 1, "high": 2}


def load_source_facts(session: Session) -> dict[str, SourceFacts]:
    """Best factuality rating (highest confidence, then newest) and newest ownership row per source."""
    best: dict[uuid.UUID, SourceRating] = {}
    for r in session.execute(select(SourceRating).where(SourceRating.dimension == "factuality")).scalars():
        cur = best.get(r.source_id)
        if cur is None or (_CONF_ORDER[r.confidence], r.retrieved_at) > (_CONF_ORDER[cur.confidence], cur.retrieved_at):
            best[r.source_id] = r
    owner: dict[uuid.UUID, SourceOwnership] = {}
    for o in session.execute(select(SourceOwnership)).scalars():
        if o.source_id not in owner or o.retrieved_at > owner[o.source_id].retrieved_at:
            owner[o.source_id] = o
    return {
        str(sid): SourceFacts(
            factuality=best[sid].value if sid in best else None,
            ownership_group=(owner[sid].parent_group or owner[sid].owner_name) if sid in owner else None,
        )
        for sid in set(best) | set(owner)
    }


def story_article_facts(
    session: Session, story_ids: list[uuid.UUID] | None = None
) -> dict[uuid.UUID, list[ArticleFacts]]:
    q = (
        select(
            StoryArticle.story_id,
            Article.id,
            Article.source_id,
            Article.language,
            Article.original_article_id,
            Framing.stance,
            Framing.stance_confidence,
        )
        .join(Article, Article.id == StoryArticle.article_id)
        .outerjoin(Framing, (Framing.article_id == Article.id) & (Framing.story_id == StoryArticle.story_id))
    )
    if story_ids is not None:
        q = q.where(StoryArticle.story_id.in_(story_ids))
    rows = session.execute(q).all()
    in_story: dict[uuid.UUID, set[uuid.UUID]] = defaultdict(set)
    for r in rows:
        in_story[r.story_id].add(r.id)
    out: dict[uuid.UUID, list[ArticleFacts]] = defaultdict(list)
    for r in rows:
        out[r.story_id].append(
            ArticleFacts(
                source_id=str(r.source_id),
                language=r.language,
                # A copy collapses into its original only when the original is in the same story.
                is_copy=r.original_article_id is not None and r.original_article_id in in_story[r.story_id],
                stance=str(r.stance) if r.stance else "unclassified",
                stance_confidence=str(r.stance_confidence) if r.stance_confidence else None,
            )
        )
    return out


def compute_all(session: Session, now: datetime, story_ids: list[uuid.UUID] | None = None) -> int:
    g = load_yaml("guardrails.yaml")
    cfg: dict[str, Any] = g["stats"]
    sources = load_source_facts(session)
    n = 0
    for story_id, arts in story_article_facts(session, story_ids).items():
        r = compute_story_stats(arts, sources, g["min_sources_for_blindspot"], cfg)
        values = {
            "story_id": story_id,
            "computed_at": now,
            "stance_counts": r.stance_counts,
            "factuality_counts": r.factuality_counts,
            "ownership_counts": r.ownership_counts,
            "language_counts": r.language_counts,
            "coverage_confidence": r.coverage_confidence,
            "blindspot_type": r.blindspot_type,
            "blindspot_skew": r.blindspot_skew,
            "blindspot_score": r.blindspot_score,
        }
        stmt = insert(StoryStats).values(**values)
        session.execute(stmt.on_conflict_do_update(index_elements=["story_id"], set_=values))
        n += 1
    return n


def main() -> int:
    configure_logging("INFO", json=False)
    with Session(get_engine()) as session, session.begin():
        n = compute_all(session, datetime.now(UTC))
    print(f"story_stats computed for {n} stories")
    return 0


if __name__ == "__main__":
    sys.exit(main())
