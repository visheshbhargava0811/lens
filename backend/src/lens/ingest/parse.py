"""Parse feed payloads into raw items: RSS/Atom (feedparser) and Google News sitemaps (stdlib XML).

Used by both feed discovery and the fetcher, so what discovery calls "usable" is exactly what
the fetcher can ingest.
"""

from __future__ import annotations

import calendar
import html
import re
import xml.etree.ElementTree as ET  # types only; parsing goes through defusedxml
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import feedparser
from defusedxml import DefusedXmlException
from defusedxml.ElementTree import fromstring as safe_fromstring

_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"\s+")


@dataclass(frozen=True)
class RawItem:
    url: str
    title: str
    snippet: str | None
    published_at: datetime | None
    byline: str | None
    language: str | None  # as declared by the feed, if any; triage detects it anyway


@dataclass(frozen=True)
class Parsed:
    kind: str  # "rss" | "sitemap" | "sitemap_index" | "unknown"
    items: list[RawItem]
    child_sitemaps: list[str]


def clean_text(value: str | None) -> str | None:
    """Strip tags and entities, collapse whitespace. Keeps the original script untouched."""
    if not value:
        return None
    text = _WS.sub(" ", html.unescape(_TAG.sub(" ", value))).strip()
    return text or None


def _struct_to_dt(st: Any) -> datetime | None:
    if not st:
        return None
    return datetime.fromtimestamp(calendar.timegm(st), tz=UTC)


def _iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def _local(el: ET.Element) -> str:
    return el.tag.rsplit("}", 1)[-1]


def _child(el: ET.Element, name: str) -> ET.Element | None:
    return next((c for c in el if _local(c) == name), None)


def _text(el: ET.Element | None, *path: str) -> str:
    for name in path:
        if el is None:
            return ""
        el = _child(el, name)
    return (el.text or "").strip() if el is not None else ""


def _parse_sitemap(root: ET.Element) -> Parsed:
    # Match by local name: some publishers declare the sitemap namespace with https:// instead of http://.
    if _local(root) == "sitemapindex":
        children = [_text(sm, "loc") for sm in root if _local(sm) == "sitemap"]
        return Parsed("sitemap_index", [], [c for c in children if c])
    items = []
    for url in (u for u in root if _local(u) == "url"):
        loc = _text(url, "loc")
        news = _child(url, "news")
        if not loc or news is None:
            continue  # only news entries carry a title and publication date
        title = clean_text(_text(news, "title"))
        if not title:
            continue
        items.append(
            RawItem(
                url=loc,
                title=title,
                snippet=None,
                published_at=_iso(_text(news, "publication_date")),
                byline=None,
                language=_text(news, "publication", "language") or None,
            )
        )
    return Parsed("sitemap", items, [])


def parse_payload(content: bytes) -> Parsed:
    head = content[:2048].lstrip()
    if b"<urlset" in head or b"<sitemapindex" in head:
        try:
            # Untrusted XML from third-party sites: defusedxml blocks entity-expansion and XXE.
            return _parse_sitemap(safe_fromstring(content))
        except (ET.ParseError, DefusedXmlException):
            return Parsed("unknown", [], [])
    d: Any = feedparser.parse(content)
    if not d.get("version") and not d.entries:
        return Parsed("unknown", [], [])
    items = []
    lang = (d.feed.get("language") or None) if d.get("feed") else None
    for e in d.entries:
        link = (e.get("link") or "").strip()
        title = clean_text(e.get("title"))
        if not link or not title:
            continue
        items.append(
            RawItem(
                url=link,
                title=title,
                snippet=clean_text(e.get("summary")),
                published_at=_struct_to_dt(e.get("published_parsed") or e.get("updated_parsed")),
                byline=clean_text(e.get("author")),
                language=lang,
            )
        )
    return Parsed("rss", items, [])
