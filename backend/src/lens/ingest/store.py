"""Turn parsed feed items into article rows: license enforcement, triage, idempotent insert,
syndication marking. docs/04 sections 1-2.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from lens.core.config_files import load_yaml
from lens.db.models import AnalysisDepth, Article, LicenseMode, Source
from lens.ingest.parse import RawItem
from lens.ingest.triage import classify_news, detect_language, detect_wire
from lens.nlp.textkeys import canonical_url, content_hash, is_near_duplicate, normalize_text, simhash64

SCHEMA_VERSION = "1"


def sanitize_published_at(
    published: datetime | None, fetched: datetime, cfg: dict[str, Any]
) -> tuple[datetime, str | None]:
    """Publish times from feeds can be wrong. Some label India time as UTC; some are simply in the future.

    Returns the time to store and a note when it was changed."""
    if published is None:
        return fetched, "missing"
    tolerance = timedelta(minutes=cfg["future_tolerance_min"])
    if published <= fetched + tolerance:
        return published, None
    shifted = published - timedelta(minutes=cfg["ist_offset_min"])
    if shifted <= fetched + tolerance:
        return shifted, "ist_labelled_as_utc"
    return fetched, "future_clamped"


@dataclass
class StoreStats:
    seen: int = 0
    inserted: int = 0
    duplicates: int = 0
    too_old: int = 0
    time_fixed: int = 0
    not_news: int = 0
    syndicated: int = 0
    inserted_ids: list[uuid.UUID] = field(default_factory=list)


def article_values(source: Source, item: RawItem, now: datetime, cfg: dict[str, Any]) -> dict[str, Any]:
    """Build a row, storing only what `license_mode` allows (rule 6). Never stores full_text or images
    unless the source is licensed for it, and full_text sources are refused by the registry for now."""
    mode = LicenseMode(source.license_mode)
    snippet = item.snippet if mode is not LicenseMode.link_only else None
    if snippet:
        snippet = snippet[: cfg["fetch"]["snippet_max_chars"]]
    depth = AnalysisDepth.snippet if snippet else AnalysisDepth.headline_only
    lang = detect_language(f"{item.title}\n{snippet or ''}", declared=item.language)
    verdict = classify_news(item.url, item.title)
    wire = detect_wire(item.byline, item.title, snippet)
    text_for_hash = f"{item.title} {snippet or ''}"
    return {
        "source_id": source.id,
        "url": item.url,
        "canonical_url": canonical_url(item.url),
        "title": item.title,
        "snippet": snippet,
        "full_text": None,  # no license, no extractor (ADR-0001); enforced again by a DB test
        "analysis_depth": depth,
        "language": lang.code,
        "language_conf": lang.confidence,
        "published_at": sanitize_published_at(item.published_at, now, cfg["fetch"])[0],
        "byline": item.byline if mode is not LicenseMode.link_only else None,
        "content_hash": content_hash(item.title, snippet),
        "simhash": simhash64(text_for_hash),
        "is_news": verdict.is_news,
        "is_opinion": verdict.is_opinion,
        "is_syndicated": wire is not None,
        "syndicated_from": wire,
        "image_url": None,  # image_policy: never fetched or stored here (docs/04)
        "schema_version": SCHEMA_VERSION,
    }


def store_items(session: Session, source: Source, items: list[RawItem], now: datetime) -> StoreStats:
    cfg = load_yaml("ingest.yaml")
    stats = StoreStats(seen=len(items))
    oldest = now - timedelta(hours=cfg["fetch"]["max_item_age_hours"])
    for item in items[: cfg["fetch"]["max_items_per_fetch"]]:
        published, note = sanitize_published_at(item.published_at, now, cfg["fetch"])
        if note in ("ist_labelled_as_utc", "future_clamped"):
            stats.time_fixed += 1
        if published < oldest:
            stats.too_old += 1
            continue
        values = article_values(source, item, now, cfg)
        if not values["is_news"]:
            stats.not_news += 1
            continue
        # Same outlet, same headline and snippet under a new URL (slug edited after a headline change,
        # or published twice): one article. Windowed so daily pieces that reuse a headline are kept.
        window = timedelta(hours=cfg["fetch"]["same_source_dup_hours"])
        if session.execute(
            select(Article.id)
            .where(
                Article.source_id == source.id,
                Article.content_hash == values["content_hash"],
                Article.published_at.between(values["published_at"] - window, values["published_at"] + window),
            )
            .limit(1)
        ).first():
            stats.duplicates += 1
            continue
        # Idempotent: the same canonical URL (or source+url) is never stored twice.
        stmt = insert(Article).values(**values).on_conflict_do_nothing().returning(Article.id)
        new_id = session.execute(stmt).scalar_one_or_none()
        if new_id is None:
            stats.duplicates += 1
            continue
        stats.inserted += 1
        stats.inserted_ids.append(new_id)
    stats.syndicated = mark_near_duplicates(session, stats.inserted_ids, now, cfg)
    return stats


def mark_near_duplicates(session: Session, article_ids: list[uuid.UUID], now: datetime, cfg: dict[str, Any]) -> int:
    """Flag copies of the same text across different sources (docs/04: SimHash, last 72 h).

    The earliest published copy is the representative; later copies point to it, so stats
    count them as one source. Returns how many articles were newly flagged."""
    if not article_ids:
        return 0
    syn = cfg["syndication"]
    window_start = now - timedelta(hours=syn["window_hours"])
    rows = session.execute(
        select(
            Article.id,
            Article.source_id,
            Article.simhash,
            Article.published_at,
            Article.title,
            Article.snippet,
            Article.syndicated_from,
            Article.original_article_id,
        ).where(Article.published_at >= window_start, Article.simhash.is_not(None))
    ).all()
    by_id = {r.id: r for r in rows}
    flagged: set[uuid.UUID] = set()
    for aid in article_ids:
        me = by_id.get(aid)
        if me is None or me.simhash is None:
            continue
        my_text = f"{me.title} {me.snippet or ''}"
        if len(normalize_text(my_text).split()) < syn["min_tokens"]:
            continue
        matches = [
            r
            for r in rows
            if r.id != me.id
            and r.source_id != me.source_id
            and r.simhash is not None
            and is_near_duplicate(
                my_text,
                f"{r.title} {r.snippet or ''}",
                me.simhash,
                r.simhash,
                syn["max_hamming"],
                syn["min_jaccard"],
            )
        ]
        if not matches:
            continue
        group = sorted([me, *matches], key=lambda r: (r.published_at, str(r.id)))
        original = group[0]
        agency = next((r.syndicated_from for r in group if r.syndicated_from), None)
        for r in group[1:]:
            if r.original_article_id == original.id:
                continue
            session.execute(
                update(Article)
                .where(Article.id == r.id)
                .values(
                    is_syndicated=True,
                    original_article_id=original.id,
                    syndicated_from=agency or r.syndicated_from,
                )
            )
            flagged.add(r.id)
    return len(flagged)
