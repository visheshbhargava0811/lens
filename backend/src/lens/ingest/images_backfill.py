"""One-off: fill `articles.image_url` for already-stored articles of hotlink sources (ADR-0034), from
each feed's current items. Feeds are fetched once, unconditionally (no ETag), through the same robots
check as ingest; fetch state is not touched. Only URLs are stored, never images.

Usage: uv run python -m lens.ingest.images_backfill
"""

from __future__ import annotations

import sys
from types import SimpleNamespace

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from lens.core.config_files import load_yaml
from lens.db.models import Article, ImagePolicy, Source, SourceFetchState
from lens.db.session import get_engine
from lens.ingest.fetcher import RobotsCache, fetch_and_parse
from lens.ingest.http import make_client


def main() -> int:
    robots = RobotsCache(ttl_s=load_yaml("ingest.yaml")["fetch"]["robots_cache_min"] * 60)
    filled = 0
    with Session(get_engine()) as session, make_client() as client:
        rows = session.execute(
            select(SourceFetchState.source_id, SourceFetchState.feed_url)
            .join(Source, Source.id == SourceFetchState.source_id)
            .where(Source.active, Source.image_policy == ImagePolicy.hotlink)
        ).all()
        for source_id, feed_url in rows:
            state = SimpleNamespace(feed_url=feed_url, etag=None, last_modified=None)  # unconditional GET
            try:
                _, parsed, error = fetch_and_parse(client, state, robots)  # type: ignore[arg-type]
            except Exception as e:  # one broken feed never stops the backfill
                print(f"{feed_url}: {type(e).__name__}")
                continue
            if error or parsed is None:
                print(f"{feed_url}: {error}")
                continue
            n = 0
            for item in parsed.items:
                if item.image_url:
                    n += session.execute(
                        update(Article)
                        .where(Article.source_id == source_id, Article.url == item.url, Article.image_url.is_(None))
                        .values(image_url=item.image_url)
                    ).rowcount  # type: ignore[attr-defined]
            with_img = sum(1 for i in parsed.items if i.image_url)
            print(f"{feed_url}: {len(parsed.items)} items, {with_img} with images, {n} articles filled")
            filled += n
        session.commit()
    print(f"filled {filled}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
