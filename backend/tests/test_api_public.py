"""Public and admin API against Postgres: shapes (docs/09), error shape, and the G-BIAS-01 contract."""

import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy.orm import Session

from lens.core.settings import get_settings
from lens.db.models import Article, Source, SourceOwnership, SourceRating, Story, StoryArticle
from lens.pipeline.stats import compute_all

pytestmark = pytest.mark.db
NOW = datetime(2026, 9, 21, 12, 0, tzinfo=UTC)
P = "/api/v1"


def _src(db: Session, slug: str, lang: str = "en") -> Source:
    s = Source(
        slug=slug, name=slug.upper(), homepage_url=f"https://{slug}.example", language_codes=[lang], region="national"
    )
    db.add(s)
    db.flush()
    return s


def _story(db: Session, sources: list[Source], minutes_ago: int = 0, slug: str | None = None) -> Story:
    t = NOW - timedelta(minutes=minutes_ago)
    story = Story(
        slug=slug or f"s-{uuid.uuid4().hex[:8]}",
        headline="Headline",
        headline_lang="en",
        first_seen_at=t,
        last_updated_at=t,
        article_count=len(sources),
        source_count=len(sources),
        languages=sorted({s.language_codes[0] for s in sources}),
    )
    db.add(story)
    db.flush()
    for i, s in enumerate(sources):
        a = Article(
            source_id=s.id,
            url=f"https://{s.slug}.example/{story.slug}",
            canonical_url=f"https://{s.slug}.example/{story.slug}",
            title=f"{s.name} headline {i}",
            analysis_depth="headline_only",
            language=s.language_codes[0],
            published_at=t,
            content_hash=uuid.uuid4().hex,
            schema_version="1",
        )
        db.add(a)
        db.flush()
        db.add(StoryArticle(story_id=story.id, article_id=a.id, method="auto"))
    db.flush()
    return story


@pytest.fixture
def seeded(db: Session) -> dict[str, Any]:
    srcs = [_src(db, f"api-{i}", "en" if i < 3 else "hi") for i in range(5)]
    for src, wording in zip(srcs, ("Left-Center", "Right-Center", "Least Biased"), strict=False):  # api-3/4 unrated
        db.add(
            SourceRating(
                source_id=src.id,
                dimension="bias",
                rater="Example Rater",
                value=wording,
                method_url="https://rater.example/method",
                retrieved_at=NOW,
                confidence="high",
            )
        )
    db.add(
        SourceRating(
            source_id=srcs[0].id,
            dimension="factuality",
            rater="Example Rater",
            value="High",
            method_url="https://rater.example/method",
            retrieved_at=NOW,
            confidence="medium",
        )
    )
    db.add(
        SourceOwnership(
            source_id=srcs[0].id,
            owner_name="Owner Zero",
            parent_group="Group Zero",
            evidence_url="https://api-0.example/about",
            retrieved_at=NOW,
            confidence="high",
        )
    )
    big = _story(db, srcs, minutes_ago=0, slug="big-story")  # 5 sources: bar available
    small = _story(db, srcs[:2], minutes_ago=10)  # 2 sources: limited coverage
    single = _story(db, srcs[:1], minutes_ago=20)  # 1 source: hidden from the feed
    killed = _story(db, srcs, minutes_ago=5)
    killed.kill_switch = True
    db.flush()
    compute_all(db, NOW)
    return {"big": big, "small": small, "single": single, "killed": killed, "sources": srcs}


def _walk(node: Any, link: str | None = None) -> Iterator[tuple[str, Any, str | None]]:
    """Yield (key, value, nearest enclosing methodology_url)."""
    if isinstance(node, dict):
        link = node.get("methodology_url") or link
        for k, v in node.items():
            yield k, v, link
            yield from _walk(v, link)
    elif isinstance(node, list):
        for v in node:
            yield from _walk(v, link)


def assert_g_bias_01(body: Any) -> None:
    """G-BIAS-01: every coverage (bias) or factuality figure has a confidence label and a
    methodology link, on the figure itself or (per-article outlet ratings) on its envelope."""
    for key, value, link in _walk(body):
        if key in ("coverage", "factuality") and isinstance(value, dict):
            assert "confidence" in value and value.get("methodology_url"), (key, value)
        if key in ("source_bias", "source_factuality") and isinstance(value, dict):
            assert "confidence" in value and link, (key, value)


def test_feed_hides_single_source_and_killed_stories(client: TestClient, seeded: dict[str, Any]) -> None:
    r = client.get(f"{P}/feed")
    assert r.status_code == 200
    assert r.headers["cache-control"] == "public, max-age=30, stale-while-revalidate=60"
    ids = [c["id"] for c in r.json()["items"]]
    assert ids == [str(seeded["big"].id), str(seeded["small"].id)]
    assert_g_bias_01(r.json())


def test_feed_cards_follow_coverage_rules(client: TestClient, seeded: dict[str, Any]) -> None:
    big, small = client.get(f"{P}/feed").json()["items"]
    assert big["coverage"]["available"] is True
    assert big["coverage"]["basis"] == "outlet_bias"
    assert big["coverage"]["buckets"] == [
        {"key": "left", "sources": 1, "pct": 20},
        {"key": "center", "sources": 1, "pct": 20},
        {"key": "right", "sources": 1, "pct": 20},
    ]
    assert big["coverage"]["unrated"] == {"sources": 2, "pct": 40}
    assert big["coverage"]["confidence"] == "medium"  # 3 of 5 outlets rated
    assert big["factuality"] == {
        "high": 1,
        "mixed": 0,
        "low": 0,
        "unrated": 4,
        "confidence": "low",
        "methodology_url": "/methodology#factuality",
    }
    assert big["counts"] == {"sources": 5, "articles": 5, "by_language": {"en": 3, "hi": 2}}
    assert small["coverage"] == {
        "available": False,
        "reason": "limited_coverage",
        "min_sources": 4,
        "confidence": "high",  # both outlets rated
        "methodology_url": "/methodology#bias",
    }
    assert big["image"] is None and big["summary_preview"] is None


def test_feed_cursor_pagination(client: TestClient, seeded: dict[str, Any]) -> None:
    first = client.get(f"{P}/feed", params={"limit": 1}).json()
    assert len(first["items"]) == 1 and first["next_cursor"]
    second = client.get(f"{P}/feed", params={"limit": 1, "cursor": first["next_cursor"]}).json()
    assert second["items"][0]["id"] == str(seeded["small"].id) and second["next_cursor"] is None


def test_bad_cursor_uses_error_shape(client: TestClient, seeded: dict[str, Any]) -> None:
    r = client.get(f"{P}/feed", params={"cursor": "garbage"})
    assert r.status_code == 400 and r.json()["error"]["code"] == "invalid_cursor"
    r = client.get(f"{P}/feed", params={"limit": 999})
    assert r.status_code == 422 and r.json()["error"]["code"] == "invalid_request"


def test_story_detail_by_id_and_slug(client: TestClient, seeded: dict[str, Any]) -> None:
    by_slug = client.get(f"{P}/stories/big-story").json()
    by_id = client.get(f"{P}/stories/{seeded['big'].id}").json()
    assert by_slug == by_id
    assert by_slug["ownership"] == {
        "groups": [{"name": "Group Zero", "sources": 1}],
        "unknown": 4,
        "methodology_url": "/methodology#ownership",
    }
    assert "2 of 5 sources have no bias rating." in by_slug["limitations"]
    assert_g_bias_01(by_slug)


def test_killed_and_missing_stories_are_404(client: TestClient, seeded: dict[str, Any]) -> None:
    for sid in (str(seeded["killed"].id), "no-such-story"):
        r = client.get(f"{P}/stories/{sid}")
        assert r.status_code == 404 and r.json()["error"]["code"] == "not_found"


def test_story_articles_carry_provenance_or_null(client: TestClient, seeded: dict[str, Any]) -> None:
    body = client.get(f"{P}/stories/big-story/articles").json()
    assert len(body["items"]) == 5
    by_src = {row["source"]["name"]: row for row in body["items"]}
    rated = by_src["API-0"]
    assert rated["source_factuality"] == {
        "rater": "Example Rater",
        "value": "High",
        "method_url": "https://rater.example/method",
        "confidence": "medium",
    }
    assert rated["source_ownership"] == {"owner": "Owner Zero", "evidence_url": "https://api-0.example/about"}
    assert by_src["API-1"]["source_factuality"] is None and by_src["API-1"]["source_ownership"] is None
    assert rated["source_bias"] == {
        "rater": "Example Rater",
        "value": "Left-Center",  # the rater's own wording on the row
        "method_url": "https://rater.example/method",
        "confidence": "high",
    }
    assert rated["bias"] == "left"
    assert by_src["API-4"]["source_bias"] is None and by_src["API-4"]["bias"] == "unrated"
    assert body["methodology_url"] == "/methodology#bias"
    assert_g_bias_01(body)
    left = client.get(f"{P}/stories/big-story/articles", params={"bias": "left"}).json()["items"]
    unrated = client.get(f"{P}/stories/big-story/articles", params={"bias": "unrated"}).json()["items"]
    assert [r["source"]["name"] for r in left] == ["API-0"]
    assert {r["source"]["name"] for r in unrated} == {"API-3", "API-4"}
    hi_only = client.get(f"{P}/stories/big-story/articles", params={"lang": "hi"}).json()
    assert {r["headline_lang"] for r in hi_only["items"]} == {"hi"}


def test_blindspots_topics_sources_methodology(client: TestClient, seeded: dict[str, Any]) -> None:
    b = client.get(f"{P}/blindspots", params={"type": "language"}).json()
    assert b["type"] == "language" and b["methodology_url"] == "/methodology#blindspots"
    assert_g_bias_01(b)
    assert client.get(f"{P}/topics").json() == {"items": []}
    srcs = client.get(f"{P}/sources").json()["items"]
    assert {"api-0", "api-4"} <= {s["slug"] for s in srcs}
    detail = client.get(f"{P}/sources/api-0").json()
    assert detail["ownership"][0]["evidence_url"] == "https://api-0.example/about"
    assert detail["ratings"][0]["method_url"] == "https://rater.example/method"
    assert str(seeded["killed"].id) not in {s["id"] for s in detail["recent_stories"]}
    assert_g_bias_01(detail)
    m = client.get(f"{P}/methodology").json()
    assert m["min_sources_for_bar"] == 4 and m["blindspot_bias_share"] == 0.7
    assert {
        "rater": "Example Rater",
        "dimension": "factuality",
        "method_url": "https://rater.example/method",
        "sources_rated": 1,
    } in m["raters"]
    assert client.get(f"{P}/sources/nope").json()["error"]["code"] == "not_found"


CSV = (
    "kind,source_slug,owner_name,evidence_url,retrieved_at,confidence\n"
    "ownership,api-1,Owner One,https://api-1.example/about,2026-09-20T00:00:00Z,high\n"
)


def test_admin_import_needs_token(client: TestClient, seeded: dict[str, Any], monkeypatch: pytest.MonkeyPatch) -> None:
    url = f"{P}/admin/sources/import"
    headers = {"content-type": "text/csv"}
    monkeypatch.setattr(get_settings(), "admin_token", None)
    assert client.post(url, content=CSV, headers=headers).status_code == 503
    monkeypatch.setattr(get_settings(), "admin_token", SecretStr("s3cret"))
    r = client.post(url, content=CSV, headers=headers | {"authorization": "Bearer wrong"})
    assert r.status_code == 401 and r.json()["error"]["code"] == "unauthorized"
    ok = {**headers, "authorization": "Bearer s3cret"}
    assert client.post(url, content=CSV, headers=ok).json() == {
        "ownership_added": 1,
        "ratings_added": 0,
        "unchanged": 0,
    }
    bad = client.post(url, content=CSV.replace("https://api-1.example/about", ""), headers=ok)
    assert bad.status_code == 422 and bad.json()["error"]["code"] == "import_rejected"
    assert "evidence_url" in bad.json()["error"]["message"]


@pytest.mark.parametrize(
    "body",
    [
        {"coverage": {"available": True, "methodology_url": "/m"}},  # no confidence
        {"factuality": {"high": 1, "confidence": "low"}},  # no methodology link
        {"items": [{"source_bias": {"value": "Left", "confidence": "low"}}]},  # no envelope link
    ],
)
def test_g_bias_01_contract_catches_missing_labels(body: dict[str, Any]) -> None:
    with pytest.raises(AssertionError):
        assert_g_bias_01(body)
