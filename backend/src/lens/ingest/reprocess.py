"""Recompute language, dedup keys and syndication for stored articles.

Run after a threshold or tokenizer change.
Usage: uv run python -m lens.ingest.reprocess
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from lens.core.config_files import load_yaml
from lens.db.models import Article, Source
from lens.db.session import get_engine
from lens.ingest.store import mark_near_duplicates, sanitize_published_at
from lens.ingest.triage import detect_language, detect_wire
from lens.nlp.textkeys import simhash64


def main() -> int:
    cfg = load_yaml("ingest.yaml")
    now = datetime.now(UTC)
    with Session(get_engine()) as session, session.begin():
        rows = session.execute(
            select(
                Article.id,
                Article.title,
                Article.snippet,
                Article.byline,
                Article.published_at,
                Article.fetched_at,
                Source.language_codes,
            ).join(Source, Source.id == Article.source_id)
        ).all()
        for r in rows:
            wire = detect_wire(r.byline, r.title, r.snippet)
            published, _ = sanitize_published_at(r.published_at, r.fetched_at, cfg["fetch"])
            # The per-item declared language is not stored; the source's language is the same declaration.
            lang = detect_language(f"{r.title}\n{r.snippet or ''}", declared=r.language_codes[0])
            session.execute(
                update(Article)
                .where(Article.id == r.id)
                .values(
                    simhash=simhash64(f"{r.title} {r.snippet or ''}"),
                    is_syndicated=wire is not None,
                    syndicated_from=wire,
                    original_article_id=None,
                    language=lang.code,
                    published_at=published,
                    language_conf=lang.confidence,
                )
            )
        ids = [r.id for r in sorted(rows, key=lambda r: r.published_at)]
        flagged = mark_near_duplicates(session, ids, now, cfg)
    print(f"reprocessed {len(rows)} articles; {flagged} near-duplicate copies linked to an original")
    return 0


if __name__ == "__main__":
    sys.exit(main())
