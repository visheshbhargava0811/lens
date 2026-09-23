"""Fetcher behavior against a fake HTTP server: conditional GET, robots, backoff, dead letters."""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from lens.db.models import Article, DeadLetter, Source, SourceFetchState
from lens.ingest.fetcher import RobotsCache, run_feed

pytestmark = pytest.mark.db
NOW = datetime(2026, 9, 21, 12, 0, tzinfo=UTC)
RSS = f"""<?xml version="1.0"?><rss version="2.0"><channel><title>t</title>
<item><title>Metro budget approved by the state cabinet</title><link>https://news.example/metro</link>
<description>The cabinet approved funds.</description><pubDate>{(NOW - timedelta(minutes=20)).strftime("%a, %d %b %Y %H:%M:%S +0000")}</pubDate></item>
</channel></rss>""".encode()


def _client(handler: Callable[[httpx.Request], httpx.Response]) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def _feed(db: Session, active: bool = True) -> SourceFetchState:
    src = Source(
        slug="news-example",
        name="News Example",
        homepage_url="https://news.example/",
        language_codes=["en"],
        region="national",
        active=active,
    )
    db.add(src)
    db.flush()
    state = SourceFetchState(
        source_id=src.id,
        feed_url="https://news.example/rss",
        kind="rss",
        interval_min=15,
        consecutive_failures=0,
    )
    db.add(state)
    db.flush()
    return state


def test_etag_is_sent_and_304_stores_nothing(db: Session) -> None:
    seen: list[str | None] = []

    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nAllow: /")
        seen.append(req.headers.get("if-none-match"))
        if req.headers.get("if-none-match") == '"v1"':
            return httpx.Response(304)
        return httpx.Response(200, content=RSS, headers={"etag": '"v1"'})

    state = _feed(db)
    with _client(handler) as c:
        first = run_feed(db, c, state, RobotsCache(3600), NOW)
        second = run_feed(db, c, state, RobotsCache(3600), NOW + timedelta(minutes=16))
    assert first.stats is not None and first.stats.inserted == 1
    assert second.not_modified and second.stats is None
    assert seen == [None, '"v1"']
    assert state.next_fetch_at == NOW + timedelta(minutes=16 + 15)
    assert db.execute(select(func.count()).select_from(Article)).scalar_one() == 1


@pytest.mark.parametrize(
    ("robots_status", "robots_body", "allowed"),
    [
        (200, "User-agent: *\nDisallow: /", False),
        (200, "User-agent: LensBot\nDisallow: /rss", False),
        (403, "", False),
        (500, "", False),
        (404, "", True),  # RFC 9309: no robots.txt means no restrictions
    ],
)
def test_robots_is_checked_at_fetch_time(db: Session, robots_status: int, robots_body: str, allowed: bool) -> None:
    fetched: list[str] = []

    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path == "/robots.txt":
            return httpx.Response(robots_status, text=robots_body)
        fetched.append(str(req.url))
        return httpx.Response(200, content=RSS)

    state = _feed(db)
    with _client(handler) as c:
        result = run_feed(db, c, state, RobotsCache(3600), NOW)
    assert (result.error is None) is allowed
    assert bool(fetched) is allowed


def test_failures_back_off_and_dead_letter_once(db: Session) -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path == "/robots.txt":
            return httpx.Response(200, text="")
        return httpx.Response(503)

    state = _feed(db)
    t = NOW
    with _client(handler) as c:
        for _ in range(7):
            run_feed(db, c, state, RobotsCache(3600), t)
            t = state.next_fetch_at
    assert state.consecutive_failures == 7
    assert state.last_error == "HTTP 503"
    assert state.last_fetched_at is not None
    assert state.next_fetch_at - state.last_fetched_at == timedelta(minutes=360)  # capped backoff
    assert db.execute(select(func.count()).select_from(DeadLetter)).scalar_one() == 1


def test_inactive_source_is_never_fetched(db: Session) -> None:
    def handler(req: httpx.Request) -> httpx.Response:  # pragma: no cover - must not be called
        raise AssertionError("fetched an inactive source")

    state = _feed(db, active=False)
    with _client(handler) as c:
        assert run_feed(db, c, state, RobotsCache(3600), NOW).error == "source inactive"


def test_feed_images_are_parsed_https_only_and_placeholders_skipped() -> None:
    from lens.ingest.parse import parse_payload

    rss = b"""<?xml version="1.0"?><rss version="2.0" xmlns:media="http://search.yahoo.com/mrss/"><channel>
    <item><title>A</title><link>https://x.in/a</link><media:content url="https://img.x.in/a.jpg" medium="image"/></item>
    <item><title>B</title><link>https://x.in/b</link><enclosure url="https://img.x.in/b.jpg" type="image/jpeg"/></item>
    <item><title>C</title><link>https://x.in/c</link><description>&lt;img src="http://img.x.in/c.jpg"&gt;</description></item>
    <item><title>D</title><link>https://x.in/d</link><media:thumbnail url="https://x.in/default_image_new.jpg"/></item>
    </channel></rss>"""
    assert [i.image_url for i in parse_payload(rss).items] == [
        "https://img.x.in/a.jpg",
        "https://img.x.in/b.jpg",
        None,
        None,
    ]
