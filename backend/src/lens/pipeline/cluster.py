"""Clusterer node (Graph 1, node 5) with persistence: assigns indexed articles to stories.

The decision logic is lens.clustering.core (the same code the eval measures). This module loads
candidate stories, applies the decision, and writes stories to Postgres and Qdrant.
"""

from __future__ import annotations

import re
import sys
import unicodedata
import uuid
from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

import numpy as np
from qdrant_client import QdrantClient, models
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from lens.clustering.core import ArticleFeatures, IncrementalClusterer, StoryState
from lens.core.config_files import load_yaml
from lens.core.logging import configure_logging, get_logger
from lens.db.models import Article, ReviewQueueItem, Story, StoryArticle, StoryStatus
from lens.db.session import get_engine
from lens.retrieval.qdrant_store import ARTICLES, STORIES, fetch_article_vectors, get_qdrant, iso

log = get_logger(__name__)
_SLUG = re.compile(r"[^a-z0-9]+")


def make_slug(headline: str, story_id: uuid.UUID) -> str:
    """URL slug from the Latin words of the headline (original script is kept in the headline itself)."""
    words = _SLUG.sub("-", headline.lower()).strip("-")
    words = "-".join(words.split("-")[:8])
    return f"{words}-{story_id.hex[:8]}" if words else f"story-{story_id.hex[:12]}"


@dataclass
class ClusterStats:
    articles: int = 0
    new_stories: int = 0
    assigned: int = 0
    syndicated: int = 0
    verifier_calls: int = 0
    decisions: Counter[str] = field(default_factory=Counter)


def _feature_key(value: str) -> str:
    """Normalize a stored entity or event type for equality without changing its display text."""
    return " ".join(unicodedata.normalize("NFC", value).casefold().split())


def _entity_keys(entities: dict[str, Any] | None) -> frozenset[str] | None:
    """Flatten the ArticleEntities schema into the normalized keys used by the cluster scorer."""
    if entities is None:
        return None  # Entity extraction has not run, so do not reweight this feature.
    keys: set[str] = set()
    for field_name in ("people", "organizations", "parties", "places"):
        values = entities.get(field_name, [])
        if isinstance(values, list):
            keys.update(_feature_key(value) for value in values if isinstance(value, str) and value.strip())
    return frozenset(keys)


def _story_feature_counts(session: Session, story_id: uuid.UUID) -> tuple[Counter[str], Counter[str]]:
    """Reconstruct candidate features from member articles; Story only stores the centroid."""
    entities: Counter[str] = Counter()
    event_types: Counter[str] = Counter()
    rows = session.execute(
        select(Article.entities, Article.event_type)
        .join(StoryArticle, StoryArticle.article_id == Article.id)
        .where(StoryArticle.story_id == story_id)
    ).all()
    for raw_entities, event_type in rows:
        keys = _entity_keys(raw_entities)
        if keys:
            entities.update(keys)
        if event_type and event_type.strip():
            event_types[_feature_key(event_type)] += 1
    return entities, event_types


def _story_vectors(client: QdrantClient, ids: list[str]) -> dict[str, np.ndarray]:
    out: dict[str, np.ndarray] = {}
    if ids:
        for rec in client.retrieve(STORIES, ids=ids, with_vectors=["dense"]):
            vec = rec.vector["dense"] if isinstance(rec.vector, dict) else rec.vector
            out[str(rec.id)] = np.asarray(vec, dtype=np.float32)
    return out


def _candidates(client: QdrantClient, vec: np.ndarray, published: datetime, cfg: dict[str, Any]) -> list[str]:
    since = published - timedelta(hours=cfg["window_hours"])
    res = client.query_points(
        STORIES,
        query=vec.tolist(),
        using="dense",
        limit=cfg["candidates"],
        query_filter=models.Filter(
            must=[models.FieldCondition(key="last_updated_at", range=models.DatetimeRange(gte=since))]
        ),
        with_payload=False,
    )
    return [str(p.id) for p in res.points]


def _write_story_point(client: QdrantClient, story: Story, centroid: np.ndarray) -> None:
    client.upsert(
        STORIES,
        points=[
            models.PointStruct(
                id=str(story.id),
                vector={"dense": centroid.tolist()},
                payload={
                    "story_id": str(story.id),
                    "topic": story.topic,
                    "region": story.region,
                    "status": story.status,
                    "last_updated_at": iso(story.last_updated_at),
                    "languages": list(story.languages or []),
                    "n": story.article_count,
                },
            )
        ],
    )


def refresh_story_counts(session: Session, story_id: uuid.UUID) -> None:
    """article_count, source_count (distinct outlets; copies of wire stories count once), languages."""
    members = (
        select(Article.source_id, Article.language, Article.original_article_id, Article.published_at)
        .join(StoryArticle, StoryArticle.article_id == Article.id)
        .where(StoryArticle.story_id == story_id)
        .subquery()
    )
    n, sources, langs, last = session.execute(
        select(
            func.count(),
            func.count(func.distinct(members.c.source_id)).filter(members.c.original_article_id.is_(None)),
            func.array_agg(func.distinct(members.c.language)),
            func.max(members.c.published_at),
        )
    ).one()
    session.execute(
        update(Story)
        .where(Story.id == story_id)
        .values(
            article_count=n,
            source_count=sources,
            languages=sorted(x for x in langs if x),
            last_updated_at=last,
        )
    )


def cluster_pending(session: Session, client: QdrantClient, limit: int = 5000) -> ClusterStats:
    cfg = load_yaml("clustering.yaml")
    stats = ClusterStats()
    in_story = select(StoryArticle.article_id).where(StoryArticle.article_id == Article.id).exists()
    arts = (
        session.execute(select(Article).where(Article.is_news, ~in_story).order_by(Article.published_at).limit(limit))
        .scalars()
        .all()
    )
    vecs = fetch_article_vectors(client, [str(a.id) for a in arts])

    for a in arts:
        vec = vecs.get(str(a.id))
        if vec is None:
            continue  # not indexed yet; picked up next run
        stats.articles += 1

        # Wire copies join their original's story (they are the same text, counted once).
        if a.original_article_id is not None:
            orig_story = session.execute(
                select(StoryArticle.story_id).where(StoryArticle.article_id == a.original_article_id)
            ).scalar_one_or_none()
            if orig_story is not None:
                session.add(StoryArticle(story_id=orig_story, article_id=a.id, similarity=1.0, method="syndication"))
                refresh_story_counts(session, uuid.UUID(str(orig_story)))
                stats.syndicated += 1
                continue

        cand_ids = _candidates(client, vec, a.published_at, cfg)
        cand_vecs = _story_vectors(client, cand_ids)
        clusterer = IncrementalClusterer(cfg, id_factory=lambda: str(uuid.uuid4()))
        for cid in cand_ids:
            cand = session.get(Story, uuid.UUID(cid))
            if cand is None or cand.kill_switch or cid not in cand_vecs:
                continue
            entities, event_types = _story_feature_counts(session, cand.id)
            clusterer.stories[cid] = StoryState(
                cid,
                cand_vecs[cid],
                cand.article_count,
                cand.first_seen_at,
                cand.last_updated_at,
                entities=entities,
                event_types=event_types,
            )
        outcome = clusterer.add(
            ArticleFeatures(
                str(a.id),
                vec,
                a.published_at,
                entities=_entity_keys(a.entities),
                event_type=_feature_key(a.event_type) if a.event_type and a.event_type.strip() else None,
            )
        )
        stats.decisions[outcome.decision] += 1
        stats.verifier_calls += outcome.verifier_called
        state = clusterer.stories[outcome.story_id]
        sid = uuid.UUID(outcome.story_id)

        story = session.get(Story, sid)
        if story is None:
            story = Story(
                id=sid,
                slug=make_slug(a.title, sid),
                headline=a.title,
                headline_lang=a.language,
                status=StoryStatus.developing,
                first_seen_at=a.published_at,
                last_updated_at=a.published_at,
                article_count=0,
                source_count=0,
                languages=[a.language],
            )
            session.add(story)
            session.flush()
            stats.new_stories += 1
            method = "auto"
        else:
            stats.assigned += 1
            method = "verifier" if outcome.verifier_verdict else "auto"
        similarity = outcome.best.parts["cos"] if outcome.best and outcome.story_id == outcome.best.story_id else 1.0
        session.add(StoryArticle(story_id=sid, article_id=a.id, similarity=similarity, method=method))
        session.flush()
        refresh_story_counts(session, sid)
        session.refresh(story)
        _write_story_point(client, story, state.centroid)
        client.set_payload(ARTICLES, payload={"story_id": str(sid)}, points=[str(a.id)])
    return stats


def _rows(result: Any) -> int:
    return int(result.rowcount)  # UPDATE returns a CursorResult


def update_lifecycle(session: Session, now: datetime) -> dict[str, int]:
    life = load_yaml("clustering.yaml")["lifecycle"]
    stable_before = now - timedelta(hours=life["stable_after_hours"])
    archive_before = now - timedelta(days=life["archive_after_days"])
    changed = {}
    changed["archived"] = _rows(
        session.execute(
            update(Story)
            .where(Story.status != StoryStatus.archived, Story.last_updated_at < archive_before)
            .values(status=StoryStatus.archived)
        )
    )
    changed["stable"] = _rows(
        session.execute(
            update(Story)
            .where(
                Story.status == StoryStatus.developing,
                Story.last_updated_at < stable_before,
                Story.last_updated_at >= archive_before,
            )
            .values(status=StoryStatus.stable)
        )
    )
    changed["developing"] = _rows(
        session.execute(
            update(Story)
            .where(Story.status == StoryStatus.stable, Story.last_updated_at >= stable_before)
            .values(status=StoryStatus.developing)
        )
    )
    return changed


def propose_merges(session: Session, client: QdrantClient, now: datetime) -> int:
    """Nightly HDBSCAN over recent article vectors. Files merge proposals; never merges (docs/04)."""
    from sklearn.cluster import HDBSCAN

    batch = load_yaml("clustering.yaml")["batch"]
    rows = session.execute(
        select(StoryArticle.article_id, StoryArticle.story_id)
        .join(Article, Article.id == StoryArticle.article_id)
        .where(Article.published_at >= now - timedelta(days=batch["days"]), Article.original_article_id.is_(None))
    ).all()
    if len(rows) < batch["min_cluster_size"] * 2:
        return 0
    vecs = fetch_article_vectors(client, [str(r.article_id) for r in rows])
    rows = [r for r in rows if str(r.article_id) in vecs]
    mat = np.stack([vecs[str(r.article_id)] for r in rows])
    labels = HDBSCAN(
        min_cluster_size=batch["min_cluster_size"], min_samples=batch["min_samples"], metric="cosine"
    ).fit_predict(mat)
    proposals = 0
    for lab in set(labels) - {-1}:
        stories = sorted({str(rows[i].story_id) for i in range(len(rows)) if labels[i] == lab})
        if len(stories) < 2:
            continue
        reason = "merge proposal (nightly HDBSCAN): " + ", ".join(stories)
        exists = session.execute(
            select(ReviewQueueItem.id).where(ReviewQueueItem.kind == "cluster", ReviewQueueItem.reason == reason)
        ).first()
        if exists is None:
            session.add(ReviewQueueItem(kind="cluster", ref_id=uuid.UUID(stories[0]), reason=reason))
            proposals += 1
    return proposals


def main() -> int:
    configure_logging("INFO", json=False)
    client = get_qdrant()
    with Session(get_engine()) as session, session.begin():
        st = cluster_pending(session, client)
        life = update_lifecycle(session, datetime.now(UTC))
    print(
        f"clustered {st.articles}: {st.new_stories} new stories, {st.assigned} assigned, "
        f"{st.syndicated} wire copies, verifier calls {st.verifier_calls}, decisions {dict(st.decisions)}; "
        f"lifecycle {life}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
