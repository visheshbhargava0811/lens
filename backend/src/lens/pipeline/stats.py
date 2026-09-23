"""Stats node (Graph 1, node 11): compute story_stats for stories whose articles changed.

Bias (Left/Center/Right) and factuality are outlet-level third-party ratings (ADR-0020). Source
facts come only from imported, provenance-backed rows (rule 7); anything missing is unrated.
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
from lens.db.models import Article, SourceOwnership, SourceRating, StoryArticle, StoryStats
from lens.db.session import get_engine
from lens.stats.coverage import ArticleFacts, SourceFacts, compute_story_stats

log = get_logger(__name__)
_CONF_ORDER = {"low": 0, "medium": 1, "high": 2}


def best_ratings(
    session: Session, dimension: str, source_ids: list[uuid.UUID] | None = None
) -> dict[uuid.UUID, SourceRating]:
    """Per source, the rating to show for one dimension: highest confidence, then newest."""
    q = select(SourceRating).where(SourceRating.dimension == dimension)
    if source_ids is not None:
        q = q.where(SourceRating.source_id.in_(source_ids))
    best: dict[uuid.UUID, SourceRating] = {}
    for r in session.execute(q).scalars():
        cur = best.get(r.source_id)
        if cur is None or (_CONF_ORDER[r.confidence], r.retrieved_at) > (_CONF_ORDER[cur.confidence], cur.retrieved_at):
            best[r.source_id] = r
    return best


def load_source_facts(session: Session) -> dict[str, SourceFacts]:
    """Bias and factuality ratings (see best_ratings) and the newest ownership row per source."""
    bias, best = best_ratings(session, "bias"), best_ratings(session, "factuality")
    owner: dict[uuid.UUID, SourceOwnership] = {}
    for o in session.execute(select(SourceOwnership)).scalars():
        if o.source_id not in owner or o.retrieved_at > owner[o.source_id].retrieved_at:
            owner[o.source_id] = o
    return {
        str(sid): SourceFacts(
            bias=bias[sid].value if sid in bias else None,
            factuality=best[sid].value if sid in best else None,
            ownership_group=(owner[sid].parent_group or owner[sid].owner_name) if sid in owner else None,
        )
        for sid in set(bias) | set(best) | set(owner)
    }


def story_article_facts(
    session: Session, story_ids: list[uuid.UUID] | None = None
) -> dict[uuid.UUID, list[ArticleFacts]]:
    q = select(
        StoryArticle.story_id,
        Article.id,
        Article.source_id,
        Article.language,
        Article.original_article_id,
    ).join(Article, Article.id == StoryArticle.article_id)
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
            "bias_counts": r.bias_counts,
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
