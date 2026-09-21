"""Ingest lag and per-source health (docs/04, docs/02 observability). Usage: make ingest-health"""

from __future__ import annotations

import sys
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from lens.db.models import Article, DeadLetter, Source, SourceFetchState
from lens.db.session import get_engine


def report(session: Session, now: datetime) -> list[dict[str, object]]:
    day = now - timedelta(hours=24)
    arts = (
        select(
            Article.source_id,
            func.count().filter(Article.fetched_at >= day).label("new_24h"),
            func.count().label("total"),
            func.max(Article.published_at).label("newest"),
            func.count().filter(Article.is_syndicated).label("syndicated"),
        )
        .group_by(Article.source_id)
        .subquery()
    )
    feeds = (
        select(
            SourceFetchState.source_id,
            func.max(SourceFetchState.last_success_at).label("last_ok"),
            func.max(SourceFetchState.consecutive_failures).label("failures"),
            func.string_agg(SourceFetchState.last_error, "; ").label("errors"),
        )
        .group_by(SourceFetchState.source_id)
        .subquery()
    )
    rows = session.execute(
        select(
            Source.slug,
            Source.language_codes,
            arts.c.new_24h,
            arts.c.total,
            arts.c.newest,
            arts.c.syndicated,
            feeds.c.last_ok,
            feeds.c.failures,
            feeds.c.errors,
        )
        .join(feeds, feeds.c.source_id == Source.id)
        .outerjoin(arts, arts.c.source_id == Source.id)
        .where(Source.active)
        .order_by(Source.slug)
    ).all()
    out = []
    for r in rows:
        out.append(
            {
                "source": r.slug,
                "lang": r.language_codes[0],
                "articles": r.total or 0,
                "new_24h": r.new_24h or 0,
                "syndicated": r.syndicated or 0,
                # Ingest lag: how stale our newest article is. Fetch lag: time since the last good fetch.
                "ingest_lag_min": round((now - r.newest).total_seconds() / 60) if r.newest else None,
                "fetch_lag_min": round((now - r.last_ok).total_seconds() / 60) if r.last_ok else None,
                "failures": r.failures or 0,
                "error": r.errors,
            }
        )
    return out


def main() -> int:
    now = datetime.now(UTC)
    with Session(get_engine()) as session:
        rows = report(session, now)
        dead = session.execute(select(func.count()).select_from(DeadLetter)).scalar_one()
    cols = [
        "source",
        "lang",
        "articles",
        "new_24h",
        "syndicated",
        "ingest_lag_min",
        "fetch_lag_min",
        "failures",
        "error",
    ]
    print(" | ".join(cols))
    for r in rows:
        print(" | ".join("" if r[c] is None else str(r[c])[:60] for c in cols))
    print(f"dead letters: {dead}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
