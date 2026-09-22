"""End-to-end: store -> index -> cluster, with in-process Qdrant and the hash embedder (no model)."""

from datetime import UTC, datetime, timedelta

import numpy as np
import pytest
from qdrant_client import QdrantClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from lens.db.models import Article, ReviewQueueItem, Source, Story, StoryArticle
from lens.ingest.parse import RawItem
from lens.ingest.store import store_items
from lens.nlp.embed import HashEmbedder
from lens.pipeline.cluster import cluster_pending, make_slug, propose_merges, update_lifecycle
from lens.pipeline.index import index_batch, unindexed
from lens.retrieval.qdrant_store import ensure_collections, upsert_article_vectors

pytestmark = pytest.mark.db
NOW = datetime(2026, 9, 21, 12, 0, tzinfo=UTC)


@pytest.fixture
def qdrant() -> QdrantClient:
    client = QdrantClient(":memory:")
    ensure_collections(client, dim=HashEmbedder.dim, colbert_dim=HashEmbedder.dim)
    return client


def _src(db: Session, slug: str) -> Source:
    s = Source(slug=slug, name=slug, homepage_url=f"https://{slug}.example", language_codes=["en"], region="national")
    db.add(s)
    db.flush()
    return s


def _ingest(db: Session, src: Source, items: list[tuple[str, str, int]]) -> None:
    store_items(
        db,
        src,
        [
            RawItem(
                url=f"https://{src.slug}.example/{u}",
                title=t,
                snippet=None,
                published_at=NOW - timedelta(minutes=m),
                byline=None,
                language=None,
            )
            for u, t, m in items
        ],
        NOW,
    )


def _pipeline(db: Session, qdrant: QdrantClient) -> None:
    index_batch(db, qdrant, HashEmbedder(), unindexed(db, 1000))
    db.flush()
    cluster_pending(db, qdrant)
    db.flush()


def test_same_event_across_outlets_forms_one_story(db: Session, qdrant: QdrantClient) -> None:
    a, b, c = _src(db, "outlet-a"), _src(db, "outlet-b"), _src(db, "outlet-c")
    # Each differs from a common base by one distinct word: every pair shares 10 of 12 words, so they
    # cluster (cosine to the centroid ~0.87) but are not wire copies (Jaccard ~0.71 < 0.75).
    _ingest(
        db,
        a,
        [
            ("1", "state cabinet okays new metro line budget for pune city on monday", 120),
            ("2", "Heavy rain floods Chennai streets overnight", 110),
        ],
    )
    _ingest(db, b, [("1", "state cabinet approves fresh metro line budget for pune city on monday", 100)])
    _ingest(db, c, [("1", "state cabinet approves new metro rail budget for pune city on monday", 90)])
    _pipeline(db, qdrant)
    stories = db.execute(select(Story).order_by(Story.article_count.desc())).scalars().all()
    assert [s.article_count for s in stories] == [3, 1]
    assert stories[0].source_count == 3 and stories[0].status == "developing"
    assert stories[0].slug.startswith("state-cabinet-okays-new-metro-line-budget")


def test_wire_copies_join_the_original_story_and_count_once(db: Session, qdrant: QdrantClient) -> None:
    a, b = _src(db, "wire-a"), _src(db, "wire-b")
    title = "Parliament passes the data protection amendment bill after a long debate"
    _ingest(db, a, [("1", title, 60)])
    _ingest(db, b, [("1", title, 30)])
    _pipeline(db, qdrant)
    [story] = db.execute(select(Story)).scalars().all()
    methods = db.execute(select(StoryArticle.method)).scalars().all()
    assert sorted(methods) == ["auto", "syndication"]
    assert story.article_count == 2 and story.source_count == 1  # the copy does not add a source


def test_rerunning_the_pipeline_is_idempotent(db: Session, qdrant: QdrantClient) -> None:
    a = _src(db, "idem-a")
    _ingest(db, a, [("1", "Budget session of parliament begins on Monday", 30)])
    _pipeline(db, qdrant)
    _pipeline(db, qdrant)
    assert db.execute(select(func.count()).select_from(StoryArticle)).scalar_one() == 1


def test_persisted_story_entities_and_event_type_influence_assignment(db: Session, qdrant: QdrantClient) -> None:
    """The second run must restore stored features rather than scoring only dense/time similarity."""
    source = _src(db, "feature-outlet")
    _ingest(db, source, [("1", "Mumbai flood update", 60)])
    first = db.execute(select(Article)).scalar_one()
    first.entities = {"people": [], "organizations": [], "parties": [], "places": ["Mumbai"]}
    first.event_type = "flood"
    db.flush()

    v1 = np.zeros(HashEmbedder.dim, dtype=np.float32)
    v1[0] = 1.0
    upsert_article_vectors(
        qdrant,
        [str(first.id)],
        np.array([v1]),
        [{"article_id": str(first.id), "published_at": first.published_at.isoformat()}],
    )
    cluster_pending(db, qdrant)
    db.flush()

    _ingest(db, source, [("2", "Mumbai flood situation", 30)])
    second = db.execute(select(Article).where(Article.id != first.id)).scalar_one()
    second.entities = {"people": [], "organizations": [], "parties": [], "places": ["Mumbai"]}
    second.event_type = "flood"
    db.flush()
    v2 = np.zeros(HashEmbedder.dim, dtype=np.float32)
    v2[:2] = (0.75, 0.6614378)  # cosine 0.75: borderline without entity/event features
    upsert_article_vectors(
        qdrant,
        [str(second.id)],
        np.array([v2]),
        [{"article_id": str(second.id), "published_at": second.published_at.isoformat()}],
    )

    cluster_pending(db, qdrant)
    assert db.execute(select(func.count()).select_from(Story)).scalar_one() == 1


def test_lifecycle_and_merge_proposals(db: Session, qdrant: QdrantClient) -> None:
    a = _src(db, "life-a")
    _ingest(db, a, [("1", "Old story about a bridge collapse in Bihar", 60 * 30)])
    _pipeline(db, qdrant)
    assert update_lifecycle(db, NOW)["stable"] == 1
    assert update_lifecycle(db, NOW + timedelta(days=8))["archived"] == 1
    assert propose_merges(db, qdrant, NOW) == 0  # too few articles; never merges on its own
    assert db.execute(select(func.count()).select_from(ReviewQueueItem)).scalar_one() == 0


def test_make_slug() -> None:
    import uuid

    sid = uuid.UUID("12345678-1234-5678-1234-567812345678")
    assert make_slug("Rain lashes Mumbai: 3 dead", sid) == "rain-lashes-mumbai-3-dead-12345678"
    assert make_slug("मुंबई में भारी बारिश", sid) == "story-123456781234"
