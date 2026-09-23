"""The retriever (Graph 2 node 4) as chosen by the Phase 5 ablation (ADR-0029).

Tier 1: dense search over story centroids, stories kept above `tier1.min_score`.
Tier 2: dense chunk search inside those stories. With no story above threshold, a global chunk
search (time window only), kept only if its best chunk clears `tier2.min_score`. Then
source-balanced selection. Empty `hits` means weak retrieval: the caller retries or abstains.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal

from qdrant_client import QdrantClient

from lens.nlp.embed import Embedder
from lens.retrieval import balance
from lens.retrieval.search import Hit, chunk_filter, dense, encode_query, hybrid, stories_dense


@dataclass(frozen=True)
class Retrieved:
    hits: list[Hit]  # balanced evidence set, best first
    story_ids: list[str]
    scope: Literal["stories", "global", "none"]
    top_score: float  # tier-1 story cosine, or the best global chunk cosine
    stories: list[tuple[str, float]] = field(default_factory=list)  # all tier-1 candidates, for "closest stories"


def retrieve(
    client: QdrantClient,
    embedder: Embedder,
    query: str,
    bias_of: Mapping[str, str],
    cfg: Mapping[str, Any],
    now: datetime,
    window_days: int | None = None,
) -> Retrieved:
    t1, t2 = cfg["tier1"], cfg["tier2"]
    days = window_days or t1["window_days"]
    q = encode_query(embedder, query, colbert=False)
    candidates = stories_dense(client, q, now, days, t1["top_stories"])
    stories = [(s, sc) for s, sc in candidates if sc >= t1["min_score"]]

    def search(story_ids: list[str] | None) -> list[Hit]:
        flt = chunk_filter(now, days, story_ids=story_ids)
        if t2["mode"] == "hybrid":
            lim = {"dense_limit": t2["dense_limit"], "sparse_limit": t2["sparse_limit"], "limit": t2["fused_limit"]}
            return hybrid(client, q, flt, rrf_k=t2["rrf_k"], **lim)
        return dense(client, q, flt, t2["fused_limit"])

    if stories:
        ids = [s for s, _ in stories]
        hits = search(ids)
        scope: Literal["stories", "global", "none"] = "stories"
        top = stories[0][1]
    else:
        hits = search(None)
        top = hits[0].score if hits else 0.0
        if top < t2["min_score"]:
            return Retrieved([], [], "none", top, candidates)
        ids = list(dict.fromkeys(h.story_id for h in hits if h.story_id))[: t1["top_stories"]]
        scope = "global"
    picked = balance.select(hits[: t2["rerank_top_k"]], bias_of, cfg["balance"])
    return Retrieved(picked, ids, scope, top, candidates)
