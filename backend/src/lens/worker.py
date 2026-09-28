"""Arq worker: a per-minute scheduler enqueues due feeds; each feed is fetched in its own job."""

from __future__ import annotations

import asyncio
import hashlib
import uuid
from datetime import UTC, datetime
from typing import Any, ClassVar

from arq.connections import ArqRedis, RedisSettings
from arq.cron import cron
from langsmith import traceable
from sqlalchemy.orm import Session

from lens.core.config_files import load_yaml
from lens.core.logging import configure_logging, get_logger
from lens.core.settings import get_settings
from lens.core.tracing import configure_tracing
from lens.db.models import SourceFetchState
from lens.db.session import get_engine
from lens.ingest.fetcher import RobotsCache, due_feeds, run_feed
from lens.ingest.http import make_client

log = get_logger(__name__)


def _job_id(source_id: uuid.UUID, feed_url: str) -> str:
    # A stable job id, not a security use of SHA-1.
    digest = hashlib.sha1(f"{source_id}|{feed_url}".encode(), usedforsecurity=False)  # nosemgrep
    return "fetch:" + digest.hexdigest()[:16]


async def schedule_due(ctx: dict[str, Any]) -> int:
    """Enqueue every due feed. The job id makes a feed's pending job unique, so slow feeds never pile up."""
    redis: ArqRedis = ctx["redis"]
    with Session(get_engine()) as session:
        due = [(s.source_id, s.feed_url) for s in due_feeds(session, datetime.now(UTC))]
    for source_id, feed_url in due:
        await redis.enqueue_job("fetch_feed", str(source_id), feed_url, _job_id=_job_id(source_id, feed_url))
    return len(due)


def _fetch_sync(source_id: str, feed_url: str, robots: RobotsCache) -> dict[str, Any]:
    with Session(get_engine()) as session, session.begin(), make_client() as client:
        state = session.get(SourceFetchState, (uuid.UUID(source_id), feed_url))
        if state is None:
            return {"skipped": "unknown feed"}
        result = run_feed(session, client, state, robots)
        return {
            "status": result.status,
            "new": result.stats.inserted if result.stats else 0,
            "error": result.error,
        }


async def fetch_feed(ctx: dict[str, Any], source_id: str, feed_url: str) -> dict[str, Any]:
    fn = _fetch_sync
    if get_settings().ingest_trace:  # off by default: one trace per fetch exhausts LangSmith quota
        fn = traceable(name="ingest.fetch_feed", run_type="tool", tags=["graph:offline", "node:fetcher"])(fn)
    return await asyncio.to_thread(fn, source_id, feed_url, ctx["robots"])


async def startup(ctx: dict[str, Any]) -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    configure_tracing(settings)
    ctx["robots"] = RobotsCache(ttl_s=load_yaml("ingest.yaml")["fetch"]["robots_cache_min"] * 60)


class WorkerSettings:
    functions: ClassVar[list[Any]] = [fetch_feed]
    cron_jobs: ClassVar[list[Any]] = [cron(schedule_due, second=0, run_at_startup=True)]
    on_startup = startup
    max_jobs = 4  # polite: at most four feeds in flight
    job_timeout = 120
    # A finished job's stored result blocks re-enqueueing its fixed _job_id (arq default: 1 h).
    keep_result = 0
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
