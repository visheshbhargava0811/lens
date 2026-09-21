"""Feed discovery: find the feeds each outlet itself advertises, and record evidence.

Nothing here is filled in from memory. For each candidate homepage we record:
- what the homepage served (status, final URL, <title>),
- feeds advertised via <link rel="alternate"> or linked from an RSS index page on the site,
- whether robots.txt lets our crawler fetch each feed,
- whether each feed parses, how many items it has and how fresh it is,
- a terms-of-use link found on the site, if any.

Output: `data/sources/discovery.json` (evidence) and `reports/feed_discovery.md` (for review).
A human then chooses feeds from these results for `sources.seed.yaml`.

Usage: uv run python -m lens.ingest.discovery [slug ...]
"""

from __future__ import annotations

import contextlib
import json
import re
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx
import yaml
from protego import Protego

from lens.core.settings import REPO_ROOT, get_settings
from lens.ingest.http import make_client
from lens.ingest.parse import parse_payload

FEED_TYPES = {"application/rss+xml", "application/atom+xml", "application/xml", "text/xml"}
INDEX_PATH = re.compile(r"/(rss|rss[-_]?feeds?|rss[-_]index|feeds)(/|\.cms|\.html?)?$", re.I)
FEED_PATH = re.compile(r"(rss|feed|\.xml$)", re.I)
SHARE_HOST = re.compile(r"facebook|twitter|x\.com|whatsapp|linkedin|telegram|pinterest|reddit", re.I)
CONVENTIONAL_PATHS = ["/feed/", "/feed", "/rss", "/rss.xml", "/feeds/rss", "/rssfeed.xml"]
PRIORITY = re.compile(r"top|latest|home|india|nation|national|news|default|desh|rashtriya|breaking", re.I)
DEPRIORITY = re.compile(
    r"web-stor|photo|video|gallery|podcast|horoscope|rashifal|astro|lifestyle|entertain|sport|cricket|tech|auto",
    re.I,
)
MAX_FEED_CHECKS = 12
TERMS_HINT = re.compile(r"terms|conditions|नियम|शर्तें", re.I)
MAX_INDEX_PAGES = 2
MAX_FEEDS_PER_SOURCE = 400  # listing only; checks are capped by MAX_FEED_CHECKS


class _LinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.title = ""
        self._in_title = False
        self.alternates: list[tuple[str, str, str]] = []  # (href, type, title)
        self.anchors: list[tuple[str, str]] = []  # (href, text)
        self._anchor: list[str] | None = None
        self._anchor_href = ""

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = {k.lower(): (v or "") for k, v in attrs}
        if tag == "title":
            self._in_title = True
        elif tag == "link" and "alternate" in a.get("rel", "").lower():
            self.alternates.append((a.get("href", ""), a.get("type", "").lower(), a.get("title", "")))
        elif tag == "a" and a.get("href"):
            self._anchor = []
            self._anchor_href = a["href"]

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self._in_title = False
        elif tag == "a" and self._anchor is not None:
            self.anchors.append((self._anchor_href, " ".join("".join(self._anchor).split())))
            self._anchor = None

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self.title += data
        if self._anchor is not None:
            self._anchor.append(data)


@dataclass
class FeedCheck:
    url: str
    found_on: str  # evidence: the page that advertised this feed
    how: str  # "link-alternate" | "rss-index-page"
    label: str = ""
    robots_allowed: bool | None = None
    status: int | None = None
    parsed: bool = False
    items: int = 0
    newest_item_at: str | None = None
    has_summaries: bool = False
    sample_titles: list[str] = field(default_factory=list)
    kind: str | None = None  # rss | sitemap | sitemap_index | unknown
    note: str | None = None
    error: str | None = None


@dataclass
class SourceDiscovery:
    slug: str
    name: str
    language: str
    homepage_tried: str
    checked_at: str
    homepage_status: int | None = None
    homepage_final_url: str | None = None
    homepage_title: str = ""
    robots_url: str | None = None
    robots_status: int | None = None
    homepage_robots_allowed: bool | None = None
    terms_url: str | None = None
    rss_index_pages: list[str] = field(default_factory=list)
    feeds: list[FeedCheck] = field(default_factory=list)
    error: str | None = None

    @property
    def usable_feeds(self) -> list[FeedCheck]:
        return [f for f in self.feeds if f.parsed and f.items > 0 and f.robots_allowed]


def _same_site(url: str, base: str) -> bool:
    a, b = urlparse(url).netloc.lower(), urlparse(base).netloc.lower()
    return ".".join(a.split(".")[-2:]) == ".".join(b.split(".")[-2:])


def _parse_html(text: str) -> _LinkParser:
    p = _LinkParser()
    with contextlib.suppress(Exception):  # malformed HTML: keep what was parsed
        p.feed(text)
    return p


def _robots(client: httpx.Client, base: str) -> tuple[str, int | None, Protego | None]:
    robots_url = urljoin(base, "/robots.txt")
    try:
        r = client.get(robots_url)
    except httpx.HTTPError:
        return robots_url, None, None
    if r.status_code >= 400:
        # No robots.txt (4xx) means no restrictions, per RFC 9309. 5xx means assume disallowed.
        return (
            robots_url,
            r.status_code,
            Protego.parse("" if r.status_code < 500 else "User-agent: *\nDisallow: /"),
        )
    return robots_url, r.status_code, Protego.parse(r.text)


def _check_feed(client: httpx.Client, fc: FeedCheck, *, follow_index: bool = True) -> None:
    try:
        r = client.get(fc.url)
        fc.status = r.status_code
        if r.status_code >= 400:
            fc.error = f"HTTP {r.status_code}"
            return
        parsed = parse_payload(r.content)
    except Exception as exc:  # network or parser failure is a finding, not a crash
        fc.error = f"{type(exc).__name__}: {exc}"[:200]
        return
    fc.kind = parsed.kind
    if parsed.kind == "sitemap_index" and follow_index and parsed.child_sitemaps:
        # One level down: prefer a child whose name says news/latest/today.
        child = sorted(parsed.child_sitemaps, key=lambda u: not re.search(r"news|latest|today", u, re.I))[0]
        fc.note = f"sitemap index; checked child {child}"
        fc.url = child
        _check_feed(client, fc, follow_index=False)
        return
    fc.parsed = parsed.kind in ("rss", "sitemap")
    fc.items = len(parsed.items)
    fc.has_summaries = any(i.snippet for i in parsed.items[:10])
    fc.sample_titles = [i.title[:120] for i in parsed.items[:3]]
    dates = [i.published_at for i in parsed.items if i.published_at]
    if dates:
        fc.newest_item_at = max(dates).isoformat()
    if not fc.parsed:
        fc.error = "not a feed or news sitemap"


def discover_source(
    client: httpx.Client, slug: str, name: str, language: str, homepage: str
) -> SourceDiscovery:
    token = get_settings().ingest_robots_token
    sd = SourceDiscovery(
        slug=slug,
        name=name,
        language=language,
        homepage_tried=homepage,
        checked_at=datetime.now(UTC).isoformat(),
    )
    try:
        r = client.get(homepage)
    except httpx.HTTPError as exc:
        sd.error = f"homepage: {type(exc).__name__}: {exc}"[:200]
        return sd
    sd.homepage_status = r.status_code
    sd.homepage_final_url = str(r.url)
    base = str(r.url)
    sd.robots_url, sd.robots_status, robots = _robots(client, base)
    if robots is not None:
        sd.homepage_robots_allowed = robots.can_fetch(base, token)
    if r.status_code >= 400:
        sd.error = f"homepage returned HTTP {r.status_code} to our crawler"
        if robots is None or sd.robots_status is None or sd.robots_status >= 400:
            return sd
        # Homepage blocked but robots.txt readable: its news sitemaps may still be served.
        for sm in list(robots.sitemaps)[:10]:
            if re.search(r"news", sm, re.I):
                sd.feeds.append(FeedCheck(url=sm, found_on=sd.robots_url or base, how="robots-sitemap"))
        for fc in sd.feeds:
            fc.robots_allowed = robots.can_fetch(fc.url, token)
            if fc.robots_allowed:
                _check_feed(client, fc)
        return sd

    page = _parse_html(r.text)
    sd.homepage_title = " ".join(page.title.split())[:160]
    seen: set[str] = set()

    def add(url: str, found_on: str, how: str, label: str) -> None:
        url = urljoin(found_on, url.strip())
        if url in seen or not url.startswith("http") or len(sd.feeds) >= MAX_FEEDS_PER_SOURCE:
            return
        seen.add(url)
        sd.feeds.append(FeedCheck(url=url, found_on=found_on, how=how, label=label[:80]))

    # News sitemaps named in robots.txt first, so a large feed index can never crowd them out.
    if robots is not None:
        for sm in list(robots.sitemaps)[:10]:
            if re.search(r"news", sm, re.I):
                add(sm, sd.robots_url or base, "robots-sitemap", "news sitemap listed in robots.txt")
    for href, typ, title in page.alternates:
        if typ in FEED_TYPES and href:
            add(href, base, "link-alternate", title)

    for href, text in page.anchors:
        if TERMS_HINT.search(text) and not sd.terms_url and _same_site(urljoin(base, href), base):
            sd.terms_url = urljoin(base, href)

    index_pages = []
    for href, _text in page.anchors:
        full = urljoin(base, href)
        # Match on the URL path, never the anchor text: in Indian news "RSS" usually names an organisation.
        if INDEX_PATH.search(urlparse(full).path) and _same_site(full, base) and full not in index_pages:
            index_pages.append(full)
    for idx in index_pages[:MAX_INDEX_PAGES]:
        if robots is not None and not robots.can_fetch(idx, token):
            continue
        try:
            ir = client.get(idx)
        except httpx.HTTPError:
            continue
        ctype = ir.headers.get("content-type", "")
        if "xml" in ctype or "rss" in ctype:  # the "index" link was itself a feed
            add(idx, base, "link-on-homepage", "")
            continue
        sd.rss_index_pages.append(str(ir.url))
        ip = _parse_html(ir.text)
        for href, typ, title in ip.alternates:
            if typ in FEED_TYPES and href:
                add(href, str(ir.url), "rss-index-page", title)
        for href, text in ip.anchors:
            full = urljoin(str(ir.url), href)
            if FEED_PATH.search(urlparse(full).path) and not SHARE_HOST.search(urlparse(full).netloc):
                add(full, str(ir.url), "rss-index-page", text)

    if not sd.feeds:
        for path in CONVENTIONAL_PATHS:
            add(urljoin(base, path), base, "conventional-path", path)

    def rank(fc: FeedCheck) -> tuple[int, int, int]:
        text = fc.url + " " + fc.label
        return (fc.how == "conventional-path", bool(DEPRIORITY.search(text)), -len(PRIORITY.findall(text)))

    sd.feeds.sort(key=rank)
    checked = 0
    host_robots: dict[str, Protego | None] = {urlparse(base).netloc: robots}
    for fc in sd.feeds:
        # Check robots.txt on the host that serves the feed, which may differ from the homepage's.
        host = urlparse(fc.url).netloc
        if host not in host_robots:
            _, status, host_robots[host] = _robots(client, fc.url)
            if status is not None and status in (401, 403):
                host_robots[host] = Protego.parse("User-agent: *\nDisallow: /")
        feed_robots = host_robots[host]
        fc.robots_allowed = feed_robots.can_fetch(fc.url, token) if feed_robots is not None else None
        if fc.robots_allowed is False or checked >= MAX_FEED_CHECKS:
            continue
        _check_feed(client, fc)
        checked += 1
        time.sleep(1.0)  # be polite; several sites rate-limit (HTTP 429)
    # Conventional-path probes that failed are not findings worth keeping.
    sd.feeds = [f for f in sd.feeds if f.how != "conventional-path" or f.parsed]
    return sd


def _report(results: list[SourceDiscovery]) -> str:
    lines = [
        "# Feed discovery",
        "",
        f"Generated {datetime.now(UTC).strftime('%Y-%m-%d %H:%M UTC')} by `make discover-feeds`. "
        "Evidence (the page each feed was found on) is in `data/sources/discovery.json`.",
        "",
        "| Outlet | Homepage | robots.txt | Feeds found | Usable | Newest item | Note |",
        "|---|---|---|---|---|---|---|",
    ]
    for sd in results:
        usable = sd.usable_feeds
        newest = max((f.newest_item_at or "" for f in usable), default="")
        note = sd.error or ("" if usable else "no usable feed found")
        blocked = sum(1 for f in sd.feeds if f.robots_allowed is False)
        if blocked:
            note = (note + f"; {blocked} feed(s) disallowed by robots.txt").strip("; ")
        lines.append(
            f"| {sd.name} | {sd.homepage_status or '-'} | {sd.robots_status or '-'} | {len(sd.feeds)} | "
            f"{len(usable)} | {newest[:16]} | {note} |"
        )
    lines += ["", "## Usable feeds per outlet", ""]
    for sd in results:
        lines.append(f"### {sd.name}")
        if sd.terms_url:
            lines.append(f"Terms link found: {sd.terms_url}")
        for f in sd.usable_feeds:
            lines.append(
                f"- `{f.url}` ({f.kind}, {f.items} items, "
                f"summaries: {'yes' if f.has_summaries else 'no'}) {f.label}"
            )
        if not sd.usable_feeds:
            lines.append("- none")
        lines.append("")
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    cands = yaml.safe_load((REPO_ROOT / "data/sources/candidates.yaml").read_text(encoding="utf-8"))
    rows = [
        (c, lang)
        for lang, key in (("en", "english"), ("hi", "hindi"), ("regional", "regional"))
        for c in cands.get(key) or []
    ]
    if argv:
        rows = [(c, lang) for c, lang in rows if c["slug"] in argv]
    out_json = REPO_ROOT / "data/sources/discovery.json"
    existing: dict[str, Any] = json.loads(out_json.read_text()) if out_json.exists() else {}
    results = []
    with make_client() as client:
        for c, lang in rows:
            sd = discover_source(client, c["slug"], c["name"], c.get("language", lang), c["homepage"])
            print(
                f"{sd.slug:20} home={sd.homepage_status} feeds={len(sd.feeds)} "
                f"usable={len(sd.usable_feeds)} {sd.error or ''}"
            )
            results.append(sd)
            existing[sd.slug] = asdict(sd)
    out_json.write_text(json.dumps(existing, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    all_results = [
        SourceDiscovery(**{**v, "feeds": [FeedCheck(**f) for f in v["feeds"]]}) for v in existing.values()
    ]
    (REPO_ROOT / "reports/feed_discovery.md").write_text(_report(all_results) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
