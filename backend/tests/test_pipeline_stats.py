"""Stats node against Postgres: syndication dedup inside a story, provenance-backed facts, upsert."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from lens.db.models import Article, Source, SourceOwnership, SourceRating, Story, StoryArticle, StoryStats
from lens.pipeline.stats import compute_all

pytestmark = pytest.mark.db
NOW = datetime(2026, 9, 21, 12, 0, tzinfo=UTC)


def _src(db: Session, slug: str) -> Source:
    s = Source(slug=slug, name=slug, homepage_url=f"https://{slug}.example", language_codes=["en"], region="national")
    db.add(s)
    db.flush()
    return s


def _art(db: Session, src: Source, n: int, lang: str = "en", original: Article | None = None) -> Article:
    a = Article(
        source_id=src.id,
        url=f"https://{src.slug}.example/{n}",
        canonical_url=f"https://{src.slug}.example/{n}",
        title=f"title {src.slug} {n}",
        analysis_depth="headline_only",
        language=lang,
        published_at=NOW - timedelta(minutes=n),
        content_hash=uuid.uuid4().hex,
        original_article_id=original.id if original else None,
        is_syndicated=original is not None,
        schema_version="1",
    )
    db.add(a)
    db.flush()
    return a


def _story(db: Session, arts: list[Article]) -> Story:
    s = Story(
        slug=f"story-{uuid.uuid4().hex[:6]}",
        headline="h",
        headline_lang="en",
        first_seen_at=NOW,
        last_updated_at=NOW,
    )
    db.add(s)
    db.flush()
    for a in arts:
        db.add(StoryArticle(story_id=s.id, article_id=a.id, method="auto"))
    db.flush()
    return s


def test_stats_dedup_copies_and_use_only_imported_facts(db: Session) -> None:
    a, b, c = _src(db, "st-a"), _src(db, "st-b"), _src(db, "st-c")
    orig = _art(db, a, 1)
    story = _story(db, [orig, _art(db, b, 2, lang="hi"), _art(db, c, 3, original=orig)])  # c only carries a copy
    db.add(
        SourceRating(
            source_id=a.id,
            dimension="factuality",
            rater="Example Rater",
            value="High",
            method_url="https://rater.example/method",
            retrieved_at=NOW,
            confidence="medium",
        )
    )
    db.add(
        SourceRating(
            source_id=b.id,
            dimension="bias",
            rater="Example Rater",
            value="Right-Center",
            method_url="https://rater.example/method",
            retrieved_at=NOW,
            confidence="high",
        )
    )
    db.add(
        SourceOwnership(
            source_id=b.id,
            owner_name="Owner B",
            parent_group="Group B",
            evidence_url="https://b.example/about",
            retrieved_at=NOW,
            confidence="high",
        )
    )
    db.flush()

    assert compute_all(db, NOW, [story.id]) == 1
    st = db.execute(select(StoryStats).where(StoryStats.story_id == story.id)).scalar_one()
    assert st.bias_counts == {"left": 0, "center": 0, "right": 1, "unrated": 1}  # c's copy collapses
    assert st.factuality_counts == {"high": 1, "mixed": 0, "low": 0, "unrated": 1}
    assert st.ownership_counts == {"unknown": 1, "Group B": 1}
    assert st.language_counts == {"en": 1, "hi": 1}
    assert st.coverage_confidence == "medium"  # half the sources have a bias rating
    assert st.blindspot_type is None

    # Re-running updates in place.
    assert compute_all(db, NOW + timedelta(hours=1), [story.id]) == 1
    computed = db.execute(select(StoryStats.computed_at).where(StoryStats.story_id == story.id)).scalar_one()
    assert computed == NOW + timedelta(hours=1)
