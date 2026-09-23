"""Phase 1A acceptance: idempotent ingestion, license enforcement, syndication on known examples."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from lens.db.models import Article, Source
from lens.ingest.parse import RawItem
from lens.ingest.store import store_items

pytestmark = pytest.mark.db
NOW = datetime(2026, 9, 21, 12, 0, tzinfo=UTC)


def _source(db: Session, slug: str, mode: str = "snippet_only") -> Source:
    s = Source(
        slug=slug,
        name=slug,
        homepage_url=f"https://{slug}.example",
        language_codes=["en"],
        region="national",
        license_mode=mode,
        image_policy="none",
    )
    db.add(s)
    db.flush()
    return s


def _item(
    url: str,
    title: str,
    snippet: str | None = "A snippet of the story.",
    minutes_ago: int = 30,
    byline: str | None = None,
) -> RawItem:
    return RawItem(
        url=url,
        title=title,
        snippet=snippet,
        published_at=NOW - timedelta(minutes=minutes_ago),
        byline=byline,
        language=None,
    )


def test_rerunning_ingestion_is_idempotent(db: Session) -> None:
    src = _source(db, "idem")
    items = [
        _item(f"https://idem.example/story-{i}?utm_source=feed", f"Headline number {i} about the budget")
        for i in range(5)
    ]
    first = store_items(db, src, items, NOW)
    # Same items again, plus tracking-parameter and trailing-slash variants of the same URLs.
    variants = [_item(f"https://idem.example/story-{i}/", f"Headline number {i} about the budget") for i in range(5)]
    second = store_items(db, src, items + variants, NOW)
    assert first.inserted == 5
    assert second.inserted == 0 and second.duplicates == 10
    assert db.execute(select(func.count()).select_from(Article).where(Article.source_id == src.id)).scalar_one() == 5


@pytest.mark.parametrize("mode", ["snippet_only", "link_only"])
def test_no_full_text_stored_for_snippet_or_link_only(db: Session, mode: str) -> None:
    src = _source(db, f"lic-{mode}", mode)
    store_items(
        db,
        src,
        [
            _item(
                f"https://lic-{mode}.example/a",
                "Metro line budget approved by cabinet",
                snippet="Long feed summary " * 10,
                byline="Staff",
            )
        ],
        NOW,
    )
    art = db.execute(select(Article).where(Article.source_id == src.id)).scalar_one()
    assert art.full_text is None
    assert art.image_url is None
    if mode == "link_only":
        assert art.snippet is None and art.byline is None
        assert art.analysis_depth == "headline_only"
    else:
        assert art.snippet is not None and len(art.snippet) <= 600
        assert art.analysis_depth == "snippet"


def test_headline_only_when_feed_has_no_snippet(db: Session) -> None:
    src = _source(db, "sitemap-like")
    store_items(db, src, [_item("https://sitemap-like.example/a", "Rain lashes Mumbai again", snippet=None)], NOW)
    art = db.execute(select(Article).where(Article.source_id == src.id)).scalar_one()
    assert art.analysis_depth == "headline_only"


def test_old_items_and_non_news_are_skipped(db: Session) -> None:
    src = _source(db, "filters")
    stats = store_items(
        db,
        src,
        [
            _item("https://filters.example/old", "An old story from last week", minutes_ago=60 * 24 * 8),
            _item("https://filters.example/astrology/aaj-ka-rashifal", "आज का राशिफल"),
            _item("https://filters.example/opinion/why", "Why the budget matters"),
        ],
        NOW,
    )
    assert (stats.too_old, stats.not_news, stats.inserted) == (1, 1, 1)
    art = db.execute(select(Article).where(Article.source_id == src.id)).scalar_one()
    assert art.is_opinion is True


# Known syndication examples: the same agency copy carried by different outlets, with the kinds of
# small edits seen in the live feeds (abbreviated words, dropped trailing attribution, curly quotes).
KNOWN_COPIES = [
    (
        "Ker Sports min says previous LDF govt facilitated failed Messi event",
        "Ker Sports min says previous LDF govt facilitated failed Messi event",
    ),
    (
        "Vande Mataram ends after 2 stanzas in K'taka Assembly, Council; BJP leaders protest",
        "Vande Mataram ends after 2 stanzas in Karnataka Assembly, Council; BJP leaders protest",
    ),
    (
        "At least three killed in Pakistani airstrike on Afghanistan",
        "At least three killed in Pakistani airstrike on Afghanistan, Tolo News reports",
    ),
    (
        "सुप्रीम कोर्ट ने अवैध निर्माण पर राज्य सरकारों से चार हफ्ते में रिपोर्ट मांगी",
        "सुप्रीम कोर्ट ने अवैध निर्माण पर राज्य सरकारों से चार हफ्ते में रिपोर्ट मांगी (भाषा)",
    ),
]


@pytest.mark.parametrize(("first", "second"), KNOWN_COPIES)
def test_known_wire_copies_are_linked_to_the_earliest(db: Session, first: str, second: str) -> None:
    a, b = _source(db, "outlet-a"), _source(db, "outlet-b")
    store_items(db, a, [_item("https://outlet-a.example/1", first, snippet=None, minutes_ago=60)], NOW)
    stats = store_items(db, b, [_item("https://outlet-b.example/1", second, snippet=None, minutes_ago=30)], NOW)
    assert stats.syndicated == 1
    orig = db.execute(select(Article).where(Article.source_id == a.id)).scalar_one()
    copy = db.execute(select(Article).where(Article.source_id == b.id)).scalar_one()
    assert copy.is_syndicated and copy.original_article_id == orig.id
    assert orig.original_article_id is None


def test_wire_dateline_sets_agency(db: Session) -> None:
    src = _source(db, "dateline")
    store_items(
        db,
        src,
        [
            _item(
                "https://dateline.example/1",
                "Rain lashes Mumbai",
                snippet="MUMBAI (PTI): Heavy rain lashed the city on Monday.",
            )
        ],
        NOW,
    )
    art = db.execute(select(Article).where(Article.source_id == src.id)).scalar_one()
    assert art.is_syndicated and art.syndicated_from == "PTI"


UNRELATED = [
    (
        "गोरखपुर रेस्टोरेंट विवाद: 550 रुपये के बिल पर पुलिसकर्मियों और कर्मचारियों में कहासुनी",
        "नोएडा में दो फूड रेस्टोरेंट पर लगा तीन लाख का जुर्माना, नियमों के उल्लंघन का आरोप",
    ),
    (
        "Two workers killed in fire at tyre oil factory in UP",
        "Two workers injured in blast at chemical factory in Gujarat",
    ),
]


@pytest.mark.parametrize(("first", "second"), UNRELATED)
def test_similar_but_different_stories_are_not_linked(db: Session, first: str, second: str) -> None:
    a, b = _source(db, "outlet-c"), _source(db, "outlet-d")
    store_items(db, a, [_item("https://outlet-c.example/1", first, snippet=None, minutes_ago=60)], NOW)
    stats = store_items(db, b, [_item("https://outlet-d.example/1", second, snippet=None, minutes_ago=30)], NOW)
    assert stats.syndicated == 0


def test_same_outlet_duplicates_are_not_called_syndication(db: Session) -> None:
    a = _source(db, "outlet-e")
    title = "Parliament passes the data protection amendment bill after a long debate"
    store_items(db, a, [_item("https://outlet-e.example/1", title, snippet=None)], NOW)
    stats = store_items(db, a, [_item("https://outlet-e.example/2", title, snippet=None)], NOW)
    assert stats.syndicated == 0
    assert stats.inserted == 0 and stats.duplicates == 1  # same outlet re-publishing under a new URL


def test_same_outlet_repeat_outside_window_is_kept(db: Session) -> None:
    # Daily pieces can reuse a headline ("Stock market today"); a new day is a new article.
    a = _source(db, "outlet-f")
    title = "Stock market opening today: will Sensex and Nifty rise or fall this morning"
    store_items(db, a, [_item("https://outlet-f.example/1", title, minutes_ago=24 * 60)], NOW)
    stats = store_items(db, a, [_item("https://outlet-f.example/2", title, minutes_ago=30)], NOW)
    assert stats.inserted == 1


@pytest.mark.parametrize(
    ("published", "expected", "note"),
    [
        (NOW - timedelta(hours=2), NOW - timedelta(hours=2), None),
        (NOW + timedelta(minutes=5), NOW + timedelta(minutes=5), None),  # within tolerance
        (NOW + timedelta(hours=5, minutes=20), NOW - timedelta(minutes=10), "ist_labelled_as_utc"),
        (NOW + timedelta(days=3), NOW, "future_clamped"),
        (None, NOW, "missing"),
    ],
)
def test_sanitize_published_at(published: datetime | None, expected: datetime, note: str | None) -> None:
    from lens.ingest.store import sanitize_published_at

    cfg = {"future_tolerance_min": 10, "ist_offset_min": 330}
    assert sanitize_published_at(published, NOW, cfg) == (expected, note)


def test_image_url_is_stored_only_for_hotlink_sources() -> None:
    from datetime import UTC, datetime

    from lens.core.config_files import load_yaml
    from lens.db.models import ImagePolicy, LicenseMode, Source
    from lens.ingest.parse import RawItem
    from lens.ingest.store import article_values

    item = RawItem("https://x.in/a", "Headline", None, None, None, "en", image_url="https://img.x.in/a.jpg")
    cfg, now = load_yaml("ingest.yaml"), datetime.now(UTC)
    src = Source(
        slug="x", name="X", homepage_url="https://x.in", language_codes=["en"], license_mode=LicenseMode.snippet_only
    )
    src.image_policy = ImagePolicy.none
    assert article_values(src, item, now, cfg)["image_url"] is None
    src.image_policy = ImagePolicy.hotlink
    assert article_values(src, item, now, cfg)["image_url"] == "https://img.x.in/a.jpg"
