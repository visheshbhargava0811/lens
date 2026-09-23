"""Retrieval building blocks (docs/05). Each variant in the ablation is a composition of these.

- `encode_query`: one BGE-M3 pass gives dense, sparse and ColBERT token vectors.
- `dense`, `sparse`, `hybrid` (RRF over dense + sparse prefetches): chunk search in Qdrant.
- `stories_dense` (tier 1 over story centroids) and `stories_from_chunks` (tier 1 by grouping chunk hits).
- `rerank_colbert`: late-interaction MaxSim over candidate chunks, with candidate token vectors
  encoded at query time (no multivector storage; see the ablation for the storage alternative).
- `BM25`: in-memory lexical floor over chunk texts.

Verified against qdrant-client 1.19 / server 1.18: `RrfQuery(rrf=Rrf(k=...))` replaces the older
`FusionQuery`, and Qdrant's default RRF k is 2 (config sets it explicitly).
"""

from __future__ import annotations

import math
from collections import Counter, defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta

import numpy as np
from qdrant_client import QdrantClient, models

from lens.nlp.embed import Embedder
from lens.nlp.textkeys import word_tokens
from lens.retrieval.qdrant_store import CHUNKS, STORIES, iso, sparse_vector


@dataclass(frozen=True)
class EncodedQuery:
    text: str
    dense: np.ndarray
    sparse: dict[int, float]
    colbert: np.ndarray | None  # (tokens, dim)


@dataclass(frozen=True)
class Hit:
    chunk_id: str
    article_id: str
    story_id: str | None
    source_id: str
    language: str
    is_syndicated: bool
    score: float


def encode_query(embedder: Embedder, text: str, colbert: bool = True) -> EncodedQuery:
    enc = embedder.encode([text], sparse=True, colbert=colbert)
    return EncodedQuery(
        text=text,
        dense=enc.dense[0],
        sparse=enc.sparse[0] if enc.sparse else {},
        colbert=enc.colbert[0] if enc.colbert else None,
    )


def chunk_filter(
    now: datetime, window_days: int, story_ids: Sequence[str] | None = None, originals_only: bool = False
) -> models.Filter:
    must: list[models.Condition] = [
        models.FieldCondition(
            key="published_at", range=models.DatetimeRange(gte=iso(now - timedelta(days=window_days)))
        )
    ]
    if story_ids is not None:
        must.append(models.FieldCondition(key="story_id", match=models.MatchAny(any=list(story_ids))))
    if originals_only:
        must.append(models.FieldCondition(key="is_syndicated", match=models.MatchValue(value=False)))
    return models.Filter(must=must)


def _hits(points: Sequence[models.ScoredPoint]) -> list[Hit]:
    out = []
    for p in points:
        pl = p.payload or {}
        out.append(
            Hit(
                chunk_id=str(pl.get("chunk_id") or p.id),
                article_id=str(pl.get("article_id")),
                story_id=pl.get("story_id"),
                source_id=str(pl.get("source_id")),
                language=str(pl.get("language")),
                is_syndicated=bool(pl.get("is_syndicated")),
                score=float(p.score),
            )
        )
    return out


def dense(client: QdrantClient, q: EncodedQuery, flt: models.Filter, limit: int) -> list[Hit]:
    r = client.query_points(
        CHUNKS, query=q.dense.tolist(), using="dense", query_filter=flt, limit=limit, with_payload=True
    )
    return _hits(r.points)


def sparse(client: QdrantClient, q: EncodedQuery, flt: models.Filter, limit: int) -> list[Hit]:
    r = client.query_points(
        CHUNKS, query=sparse_vector(q.sparse), using="sparse", query_filter=flt, limit=limit, with_payload=True
    )
    return _hits(r.points)


def hybrid(
    client: QdrantClient,
    q: EncodedQuery,
    flt: models.Filter,
    *,
    dense_limit: int,
    sparse_limit: int,
    limit: int,
    rrf_k: int,
) -> list[Hit]:
    r = client.query_points(
        CHUNKS,
        prefetch=[
            models.Prefetch(query=q.dense.tolist(), using="dense", limit=dense_limit, filter=flt),
            models.Prefetch(query=sparse_vector(q.sparse), using="sparse", limit=sparse_limit, filter=flt),
        ],
        query=models.RrfQuery(rrf=models.Rrf(k=rrf_k)),
        limit=limit,
        with_payload=True,
    )
    return _hits(r.points)


def stories_dense(
    client: QdrantClient, q: EncodedQuery, now: datetime, window_days: int, top: int
) -> list[tuple[str, float]]:
    """Tier 1 over story centroids: (story_id, cosine) best first. The score feeds `tier1.min_score`."""
    flt = models.Filter(
        must=[
            models.FieldCondition(
                key="last_updated_at", range=models.DatetimeRange(gte=iso(now - timedelta(days=window_days)))
            )
        ]
    )
    r = client.query_points(
        STORIES, query=q.dense.tolist(), using="dense", query_filter=flt, limit=top, with_payload=True
    )
    return [(str((p.payload or {}).get("story_id") or p.id), float(p.score)) for p in r.points]


def stories_from_chunks(hits: Sequence[Hit], top: int) -> list[str]:
    """Tier 1 without story sparse vectors: rank stories by their best chunk in a hybrid hit list."""
    seen: list[str] = []
    for h in hits:
        if h.story_id and h.story_id not in seen:
            seen.append(h.story_id)
        if len(seen) == top:
            break
    return seen


def maxsim(query_tokens: np.ndarray, doc_tokens: np.ndarray) -> float:
    """ColBERT late interaction: for each query token, its best-matching doc token; summed."""
    return float((query_tokens @ doc_tokens.T).max(axis=1).sum())


def rerank_colbert(
    q: EncodedQuery, hits: Sequence[Hit], texts: dict[str, str], embedder: Embedder, top_k: int
) -> list[Hit]:
    """Rerank by MaxSim, encoding candidate token vectors at query time (no stored multivectors)."""
    if q.colbert is None or not hits:
        return list(hits)[:top_k]
    cand = [h for h in hits if h.chunk_id in texts]
    enc = embedder.encode([texts[h.chunk_id] for h in cand], sparse=False, colbert=True)
    assert enc.colbert is not None
    scored = [(maxsim(q.colbert, vecs), h) for h, vecs in zip(cand, enc.colbert, strict=True)]
    scored.sort(key=lambda s: -s[0])
    return [Hit(**{**h.__dict__, "score": s}) for s, h in scored[:top_k]]


class BM25:
    """Okapi BM25 over chunk texts, Indic-aware tokens. In memory: the lexical floor for the ablation."""

    def __init__(self, docs: dict[str, str], k1: float = 1.5, b: float = 0.75) -> None:
        self.k1, self.b = k1, b
        self.ids = list(docs)
        self.tf = [Counter(word_tokens(docs[i])) for i in self.ids]
        self.len = [sum(t.values()) for t in self.tf]
        self.avg = sum(self.len) / len(self.len) if self.len else 0.0
        df: Counter[str] = Counter()
        for t in self.tf:
            df.update(t.keys())
        n = len(self.ids)
        self.idf = {w: math.log(1 + (n - d + 0.5) / (d + 0.5)) for w, d in df.items()}
        self.postings: dict[str, list[int]] = defaultdict(list)
        for i, t in enumerate(self.tf):
            for w in t:
                self.postings[w].append(i)

    def search(self, query: str, limit: int) -> list[tuple[str, float]]:
        scores: dict[int, float] = defaultdict(float)
        for w in set(word_tokens(query)):
            idf = self.idf.get(w)
            if idf is None:
                continue
            for i in self.postings[w]:
                f = self.tf[i][w]
                scores[i] += idf * f * (self.k1 + 1) / (f + self.k1 * (1 - self.b + self.b * self.len[i] / self.avg))
        best = sorted(scores.items(), key=lambda kv: -kv[1])[:limit]
        return [(self.ids[i], s) for i, s in best]
