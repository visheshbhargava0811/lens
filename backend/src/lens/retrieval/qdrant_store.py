"""Qdrant collections (docs/03) and writes. Verified against qdrant-client 1.19 (ADR-0016)."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache

import numpy as np
from qdrant_client import QdrantClient, models

from lens.core.settings import get_settings

CHUNKS, STORIES, FACT_CHECKS, ARTICLES = "chunks", "stories", "fact_checks", "articles"


@lru_cache
def get_qdrant() -> QdrantClient:
    s = get_settings()
    key = s.qdrant_api_key.get_secret_value() if s.qdrant_api_key else None
    # A key over plain HTTP to a local server would leak it and is ignored by an unsecured server.
    return QdrantClient(url=s.qdrant_url, api_key=key if s.qdrant_url.startswith("https") else None)


def ensure_collections(client: QdrantClient, dim: int = 1024, colbert_dim: int = 1024) -> None:
    """Create missing collections and payload indexes. Idempotent."""
    existing = {c.name for c in client.get_collections().collections}
    cosine = models.Distance.COSINE
    if CHUNKS not in existing:
        client.create_collection(
            CHUNKS,
            vectors_config={
                "dense": models.VectorParams(size=dim, distance=cosine),
                "colbert": models.VectorParams(
                    size=colbert_dim,
                    distance=cosine,
                    multivector_config=models.MultiVectorConfig(comparator=models.MultiVectorComparator.MAX_SIM),
                    hnsw_config=models.HnswConfigDiff(m=0),  # rerank only, no graph
                ),
            },
            sparse_vectors_config={"sparse": models.SparseVectorParams()},
        )
    if STORIES not in existing:
        client.create_collection(
            STORIES,
            vectors_config={"dense": models.VectorParams(size=dim, distance=cosine)},
            sparse_vectors_config={"sparse": models.SparseVectorParams()},
        )
    if FACT_CHECKS not in existing:
        client.create_collection(FACT_CHECKS, vectors_config={"dense": models.VectorParams(size=dim, distance=cosine)})
    if ARTICLES not in existing:
        client.create_collection(ARTICLES, vectors_config={"dense": models.VectorParams(size=dim, distance=cosine)})

    k, dt, b = (
        models.PayloadSchemaType.KEYWORD,
        models.PayloadSchemaType.DATETIME,
        models.PayloadSchemaType.BOOL,
    )
    indexes = {
        CHUNKS: {
            "story_id": k,
            "source_id": k,
            "article_id": k,
            "language": k,
            "published_at": dt,
            "is_syndicated": b,
        },
        STORIES: {"status": k, "topic": k, "region": k, "last_updated_at": dt},
        ARTICLES: {"source_id": k, "language": k, "published_at": dt, "story_id": k, "is_syndicated": b},
        FACT_CHECKS: {"source_id": k, "language": k, "published_at": dt},
    }
    for coll, fields in indexes.items():
        for name, schema in fields.items():
            client.create_payload_index(coll, name, field_schema=schema)


@dataclass
class ChunkPoint:
    point_id: str
    dense: np.ndarray
    sparse: dict[int, float]
    payload: dict[str, object]


def sparse_vector(weights: dict[int, float]) -> models.SparseVector:
    items = sorted(weights.items())
    return models.SparseVector(indices=[i for i, _ in items], values=[v for _, v in items])


def upsert_chunks(client: QdrantClient, points: Sequence[ChunkPoint]) -> None:
    if not points:
        return
    client.upsert(
        CHUNKS,
        points=[
            models.PointStruct(
                id=p.point_id,
                vector={"dense": p.dense.tolist(), "sparse": sparse_vector(p.sparse)},
                payload=p.payload,
            )
            for p in points
        ],
    )


def upsert_article_vectors(
    client: QdrantClient, ids: Sequence[str], vectors: np.ndarray, payloads: Sequence[dict[str, object]]
) -> None:
    if not ids:
        return
    client.upsert(
        ARTICLES,
        points=[
            models.PointStruct(id=i, vector={"dense": v.tolist()}, payload=p)
            for i, v, p in zip(ids, vectors, payloads, strict=True)
        ],
    )


def fetch_article_vectors(client: QdrantClient, ids: Sequence[str]) -> dict[str, np.ndarray]:
    out: dict[str, np.ndarray] = {}
    for start in range(0, len(ids), 256):
        for rec in client.retrieve(ARTICLES, ids=list(ids[start : start + 256]), with_vectors=["dense"]):
            vec = rec.vector["dense"] if isinstance(rec.vector, dict) else rec.vector
            out[str(rec.id)] = np.asarray(vec, dtype=np.float32)
    return out


def iso(dt: datetime) -> str:
    return dt.isoformat()
