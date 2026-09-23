"""Freshness for Ask (Graph 2 node 5, docs/06): when retrieval is weak or stale, run the mini offline
pipeline on the newest articles the ingest worker has already fetched but the pipeline has not yet
indexed (up to 15 minutes of backlog), within `freshness.max_articles` and `freshness.timeout_s`.

Feeds are not fetched here: the ingest worker owns fetch state (ETags, backoff), and a second fetcher
would race it (ADR-0033). Skipped when the pipeline worker holds the pipeline lock.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from qdrant_client import QdrantClient
from sqlalchemy.orm import Session

from lens.db.locks import pipeline_lock
from lens.db.session import get_engine
from lens.nlp.embed import Embedder
from lens.pipeline.cluster import cluster_pending
from lens.pipeline.index import index_batch, unindexed


@dataclass(frozen=True)
class FreshnessResult:
    ran: bool
    reason: str
    indexed: int = 0
    clustered: int = 0
    seconds: float = 0.0


def refresh(client: QdrantClient, embedder: Embedder, cfg: dict[str, Any]) -> FreshnessResult:
    if not cfg["enabled"]:
        return FreshnessResult(False, "disabled")
    t0 = time.monotonic()
    with pipeline_lock(wait=False) as got:
        if not got:
            return FreshnessResult(False, "pipeline running")
        with Session(get_engine()) as session, session.begin():
            batch = unindexed(session, cfg["max_articles"], newest_first=True)
            if not batch:
                return FreshnessResult(False, "nothing new", seconds=round(time.monotonic() - t0, 2))
            idx = index_batch(session, client, embedder, batch)
            ids = [a.id for a, _ in batch]
        if time.monotonic() - t0 > cfg["timeout_s"]:
            # Indexed but not clustered: tier 2 finds them through the global search; the pipeline clusters them.
            return FreshnessResult(True, "timeout before clustering", idx.articles, 0, round(time.monotonic() - t0, 2))
        with Session(get_engine()) as session, session.begin():
            cl = cluster_pending(session, client, article_ids=ids)
    return FreshnessResult(True, "ok", idx.articles, cl.articles, round(time.monotonic() - t0, 2))
