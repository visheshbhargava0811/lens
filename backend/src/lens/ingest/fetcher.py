"""Fetcher (docs/04 section 1): robots.txt at fetch time, conditional GET, parse, store, reschedule."""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urljoin, urlsplit

import httpx
from protego import Protego
from sqlalchemy import select
from sqlalchemy.orm import Session

from lens.core.config_files import load_yaml
from lens.core.logging import get_logger
from lens.core.settings import get_settings
from lens.db.models import DeadLetter, Source, SourceFetchState
from lens.ingest.parse import Parsed, parse_payload
from lens.ingest.store import StoreStats, store_items

log = get_logger(__name__)


class RobotsCache:
    """robots.txt per host, re-read after `ttl` seconds. Missing (404/410) = allowed per RFC 9309;
    blocked (401/403), server errors and network failures = disallowed."""

    def __init__(self, ttl_s: float) -> None:
        self.ttl_s = ttl_s
        self._cache: dict[str, tuple[float, Protego | None]] = {}

    def allowed(self, client: httpx.Client, url: str) -> bool:
        parts = urlsplit(url)
        host = f"{parts.scheme}://{parts.netloc}"
        hit = self._cache.get(host)
        if hit is None or time.monotonic() - hit[0] > self.ttl_s:
            try:
                r = client.get(urljoin(host, "/robots.txt"))
                if r.status_code < 400:
                    parsed = Protego.parse(r.text)
                elif r.status_code in (404, 410):
                    parsed = Protego.parse("")  # RFC 9309: no robots.txt means no restrictions
                else:
                    parsed = None  # 401/403/5xx: treat as disallowed
            except httpx.HTTPError:
                parsed = None
            hit = (time.monotonic(), parsed)
            self._cache[host] = hit
        robots = hit[1]
        return robots is not None and bool(robots.can_fetch(url, get_settings().ingest_robots_token))


@dataclass
class FetchResult:
    status: int | None
    not_modified: bool = False
    stats: StoreStats | None = None
    error: str | None = None


def _get(client: httpx.Client, url: str, state: SourceFetchState | None) -> httpx.Response:
    headers = {}
    if state is not None and state.etag:
        headers["If-None-Match"] = state.etag
    if state is not None and state.last_modified:
        headers["If-Modified-Since"] = state.last_modified
    return client.get(url, headers=headers)


def fetch_and_parse(
    client: httpx.Client, state: SourceFetchState, robots: RobotsCache
) -> tuple[httpx.Response | None, Parsed | None, str | None]:
    if not robots.allowed(client, state.feed_url):
        return None, None, "robots.txt disallows or could not be read"
    r = _get(client, state.feed_url, state)
    if r.status_code == 304:
        return r, None, None
    if r.status_code >= 400:
        return r, None, f"HTTP {r.status_code}"
    parsed = parse_payload(r.content)
    if parsed.kind == "sitemap_index" and parsed.child_sitemaps:
        child = sorted(parsed.child_sitemaps, key=lambda u: "news" not in u.lower())[0]
        if not robots.allowed(client, child):
            return r, None, "robots.txt disallows sitemap child"
        parsed = parse_payload(client.get(child).content)
    if parsed.kind not in ("rss", "sitemap"):
        return r, None, "payload is not a feed or news sitemap"
    return r, parsed, None


def run_feed(
    session: Session,
    client: httpx.Client,
    state: SourceFetchState,
    robots: RobotsCache,
    now: datetime | None = None,
) -> FetchResult:
    """Fetch one feed and store its items. Updates the fetch state in the same transaction."""
    now = now or datetime.now(UTC)
    cfg: dict[str, Any] = load_yaml("ingest.yaml")["fetch"]
    source = session.get(Source, state.source_id)
    if source is None or not source.active:
        return FetchResult(status=None, error="source inactive")

    state.last_fetched_at = now
    try:
        resp, parsed, error = fetch_and_parse(client, state, robots)
    except httpx.HTTPError as exc:
        resp, parsed, error = None, None, f"{type(exc).__name__}: {exc}"[:300]

    result = FetchResult(status=resp.status_code if resp is not None else None, error=error)
    state.last_status = result.status
    if error is None:
        if resp is not None and resp.status_code == 304:
            result.not_modified = True
            state.last_new = 0
        elif parsed is not None:
            result.stats = store_items(session, source, parsed.items, now)
            state.last_items, state.last_new = len(parsed.items), result.stats.inserted
        if resp is not None:
            state.etag = resp.headers.get("etag") or state.etag
            state.last_modified = resp.headers.get("last-modified") or state.last_modified
        state.last_success_at = now
        state.last_error = None
        state.consecutive_failures = 0
        state.next_fetch_at = now + timedelta(minutes=state.interval_min)
    else:
        state.consecutive_failures += 1
        state.last_error = error
        backoff = min(state.interval_min * 2**state.consecutive_failures, cfg["max_backoff_min"])
        state.next_fetch_at = now + timedelta(minutes=backoff)
        if state.consecutive_failures == cfg["dead_letter_after_failures"]:
            session.add(
                DeadLetter(
                    stage="fetch",
                    payload={
                        "source_id": str(state.source_id),
                        "feed_url": state.feed_url,
                        "status": result.status,
                    },
                    error=error,
                    attempts=state.consecutive_failures,
                )
            )
    log.info(
        "ingest.fetch",
        source=source.slug,
        feed=state.feed_url,
        status=result.status,
        not_modified=result.not_modified,
        new=result.stats.inserted if result.stats else 0,
        duplicates=result.stats.duplicates if result.stats else 0,
        syndicated=result.stats.syndicated if result.stats else 0,
        time_fixed=result.stats.time_fixed if result.stats else 0,
        error=error,
    )
    return result


def due_feeds(session: Session, now: datetime) -> list[SourceFetchState]:
    return list(
        session.execute(
            select(SourceFetchState)
            .join(Source, Source.id == SourceFetchState.source_id)
            .where(Source.active, SourceFetchState.next_fetch_at <= now)
            .order_by(SourceFetchState.next_fetch_at)
        ).scalars()
    )
