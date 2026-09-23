"""Pipeline worker: keeps stories fresh as the ingest worker adds articles (docs/04, Scheduling).

Runs on the host (it needs the `ml` extra for BGE-M3; the ingest container does not carry it):
    make pipeline-worker
Every `pipeline.interval_min` it indexes new articles, clusters them, updates story lifecycle,
recomputes story_stats, and runs LLM analysis on eligible stories within a time budget.
Its own Arq queue keeps it apart from the ingest worker's fetch jobs.
"""

from __future__ import annotations

import asyncio
import time
from datetime import UTC, datetime
from typing import Any, ClassVar

from arq.connections import RedisSettings
from arq.cron import cron
from sqlalchemy.orm import Session

from lens.core.config_files import load_yaml
from lens.core.logging import configure_logging, get_logger
from lens.core.settings import get_settings
from lens.db.session import get_engine
from lens.nlp.embed import get_embedder
from lens.pipeline.analyze import analyze_pending
from lens.pipeline.cluster import cluster_pending, update_lifecycle
from lens.pipeline.index import index_pending
from lens.pipeline.stats import compute_all
from lens.retrieval.qdrant_store import get_qdrant

log = get_logger(__name__)
QUEUE = "lens:pipeline"


def run_once(now: datetime | None = None) -> dict[str, Any]:
    """One pass: index -> cluster -> lifecycle -> stats. Each step commits on its own, so a
    failure later in the pass never loses earlier work, and the next pass picks up the rest."""
    now = now or datetime.now(UTC)
    t0 = time.monotonic()
    idx = index_pending()
    with Session(get_engine()) as session, session.begin():
        cl = cluster_pending(session, get_qdrant())
        life = update_lifecycle(session, now)
    with Session(get_engine()) as session, session.begin():
        # ponytail: recomputes every story (~12 s for 15k); restrict to touched stories if it grows slow.
        stats = compute_all(session, now)
    # LLM analysis for 4+ source stories, time-boxed (ADR-0022); can be paused to leave quota for Ask (ADR-0030).
    analysed = analyze_pending() if load_yaml("clustering.yaml")["analysis"]["scheduled"] else "paused"
    out = {
        "indexed": idx.articles,
        "clustered": cl.articles,
        "new_stories": cl.new_stories,
        "assigned": cl.assigned,
        "lifecycle": life,
        "stats": stats,
        "analysed": analysed,
        "seconds": round(time.monotonic() - t0, 1),
    }
    log.info("pipeline.run", **out)
    return out


async def run_pipeline(ctx: dict[str, Any]) -> dict[str, Any]:
    return await asyncio.to_thread(run_once)


async def startup(ctx: dict[str, Any]) -> None:
    configure_logging(get_settings().log_level)
    await asyncio.to_thread(get_embedder)  # load the model once, before the first run


_every = load_yaml("ingest.yaml")["pipeline"]["interval_min"]


class PipelineSettings:
    functions: ClassVar[list[Any]] = []
    cron_jobs: ClassVar[list[Any]] = [
        cron(run_pipeline, minute=set(range(0, 60, _every)), run_at_startup=True, timeout=3600)
    ]
    on_startup = startup
    queue_name = QUEUE
    max_jobs = 1  # passes never overlap
    keep_result = 0
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
