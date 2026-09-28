"""Pipeline worker: keeps stories fresh as the ingest worker adds articles (docs/04, Scheduling).

Runs as the `pipeline` container (`make pipeline-up`, ADR-0038); `make pipeline-worker` runs it in the
foreground for development. Every `pipeline.interval_min` it indexes new articles, clusters them,
updates story lifecycle, recomputes story_stats, scores sampled Ask turns and queues failed guard runs
for review (docs/08), and runs LLM analysis on eligible stories within a time budget.
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
from lens.db.checkpoint import ask_checkpointer
from lens.db.locks import pipeline_lock
from lens.db.session import get_engine
from lens.nlp.embed import get_embedder
from lens.pipeline.analyze import analyze_pending
from lens.pipeline.cluster import cluster_pending, update_lifecycle
from lens.pipeline.index import index_pending
from lens.pipeline.stats import compute_all
from lens.retrieval.qdrant_store import get_qdrant
from lens.services.ask import purge_ask_turns

log = get_logger(__name__)
QUEUE = "lens:pipeline"


def factchecks_pass() -> dict[str, Any]:
    """docs/04 s9: ClaimReview ingest every `ingest.every_hours` (a Redis key with a TTL gates it, so restarts
    and parallel workers never double-run it), then verify new story claims against fact-checks."""
    import redis

    from lens.factchecks.ingest import ingest
    from lens.factchecks.match import match_claims
    from lens.llm.client import structured

    out: dict[str, Any] = {}
    cfg = load_yaml("factchecks.yaml")["ingest"]
    try:
        r = redis.Redis.from_url(get_settings().redis_url)
        if get_settings().google_factcheck_api_key and r.set(
            "lens:factchecks:ingest", "1", nx=True, ex=cfg["every_hours"] * 3600
        ):
            with Session(get_engine()) as session, session.begin():
                out["ingest"] = ingest(session, get_qdrant(), get_embedder())
    except Exception as e:
        log.warning("factchecks.ingest_failed", error=f"{type(e).__name__}: {e}"[:300])
    try:
        with Session(get_engine()) as session, session.begin():
            out["match"] = match_claims(session, get_qdrant(), get_embedder(), structured)
    except Exception as e:
        log.warning("factchecks.match_failed", error=f"{type(e).__name__}: {e}"[:300])
    return out


def memory_pass(now: datetime) -> dict[str, Any]:
    """docs/11: retention purge of story views, then consolidation for consented users who are due."""
    from lens.llm.client import structured
    from lens.memory import consolidate, store

    out: dict[str, Any] = {}
    try:
        with Session(get_engine()) as session, session.begin():
            out["views_purged"] = store.purge(session, now)
            out["consolidation"] = consolidate.run(session, structured, now)
    except Exception as e:
        log.warning("memory.pass_failed", error=f"{type(e).__name__}: {e}"[:300])
    return out


def llmops_pass(now: datetime) -> dict[str, Any]:
    """Online evaluators on sampled Ask turns, then failed guard runs into the annotation queue."""
    from langsmith import Client

    from lens.core.tracing import configure_tracing
    from lens.llm.client import structured
    from lens.ops import annotation, online_eval

    if get_settings().langsmith_api_key is None:
        return {"skipped": "no LANGSMITH_API_KEY"}
    configure_tracing(get_settings())
    out: dict[str, Any] = {}
    try:
        with Session(get_engine()) as session, session.begin():
            out["online_eval"] = online_eval.run(session, structured, now, feedback=Client().create_feedback)
    except Exception as e:
        log.warning("llmops.online_eval_failed", error=f"{type(e).__name__}: {e}"[:300])
    try:
        out["annotation"] = annotation.sweep(now=now)
    except Exception as e:
        log.warning("llmops.sweep_failed", error=f"{type(e).__name__}: {e}"[:300])
    return out


def run_once(now: datetime | None = None) -> dict[str, Any]:
    """One pass: index -> cluster -> lifecycle -> stats. Each step commits on its own, so a
    failure later in the pass never loses earlier work, and the next pass picks up the rest."""
    now = now or datetime.now(UTC)
    t0 = time.monotonic()
    with pipeline_lock(wait=True):  # shared with Ask's freshness node, so no article is processed twice
        idx = index_pending()
        with Session(get_engine()) as session, session.begin():
            cl = cluster_pending(session, get_qdrant())
            life = update_lifecycle(session, now)
    with Session(get_engine()) as session, session.begin():
        # ponytail: recomputes every story (~12 s for 15k); restrict to touched stories if it grows slow.
        stats = compute_all(session, now)
        purged = purge_ask_turns(session, now, ask_checkpointer())  # docs/03 retention for Ask turns
    fc = factchecks_pass()
    mem = memory_pass(now)
    ops = llmops_pass(now)  # docs/08 review loop and online evals; best effort, never blocks the pipeline
    # LLM analysis for 4+ source stories, time-boxed (ADR-0022); can be paused to leave quota for Ask (ADR-0030).
    analysed = analyze_pending() if load_yaml("clustering.yaml")["analysis"]["scheduled"] else "paused"
    out = {
        "indexed": idx.articles,
        "clustered": cl.articles,
        "new_stories": cl.new_stories,
        "assigned": cl.assigned,
        "lifecycle": life,
        "stats": stats,
        "ask_turns_purged": purged,
        "analysed": analysed,
        "factchecks": fc,
        "memory": mem,
        "llmops": ops,
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
