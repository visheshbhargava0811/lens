"""Fetch every active feed once, in-process (no Redis). Usage: uv run python -m lens.ingest.run_once"""

from __future__ import annotations

import sys
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from lens.core.config_files import load_yaml
from lens.core.logging import configure_logging
from lens.db.models import Source, SourceFetchState
from lens.db.session import get_engine
from lens.ingest.fetcher import RobotsCache, run_feed
from lens.ingest.http import make_client


def main() -> int:
    configure_logging("INFO", json=False)
    robots = RobotsCache(ttl_s=load_yaml("ingest.yaml")["fetch"]["robots_cache_min"] * 60)
    with Session(get_engine()) as session, make_client() as client:
        states = (
            session.execute(
                select(SourceFetchState).join(Source, Source.id == SourceFetchState.source_id).where(Source.active)
            )
            .scalars()
            .all()
        )
        for state in states:
            with session.begin_nested():
                run_feed(session, client, state, robots, datetime.now(UTC))
            session.commit()
    return 0


if __name__ == "__main__":
    sys.exit(main())
