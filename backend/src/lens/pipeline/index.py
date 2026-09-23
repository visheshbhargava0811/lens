"""Chunk and embed (Graph 1, node 4): chunk rows in Postgres, vectors in Qdrant. Idempotent by article."""

from __future__ import annotations

import sys
import uuid
from dataclasses import dataclass

from qdrant_client import QdrantClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from lens.core.logging import configure_logging, get_logger
from lens.db.models import Article, Chunk, Source
from lens.db.session import get_engine
from lens.nlp.chunking import Chunk as TextChunk
from lens.nlp.chunking import chunk_article
from lens.nlp.embed import Embedder, article_text, chunk_embed_text, get_embedder
from lens.retrieval.qdrant_store import (
    ChunkPoint,
    ensure_collections,
    get_qdrant,
    iso,
    upsert_article_vectors,
    upsert_chunks,
)

log = get_logger(__name__)
_NS = uuid.UUID("5b0c3f0e-6a55-4b43-9a4c-1f6f0e2a9d11")  # namespace for deterministic chunk point ids


@dataclass
class IndexStats:
    articles: int = 0
    chunks: int = 0


def unindexed(session: Session, limit: int, newest_first: bool = False) -> list[tuple[Article, Source]]:
    has_chunk = select(Chunk.article_id).where(Chunk.article_id == Article.id).exists()
    order = Article.published_at.desc() if newest_first else Article.published_at
    rows = session.execute(
        select(Article, Source)
        .join(Source, Source.id == Article.source_id)
        .where(Article.is_news, ~has_chunk)
        .order_by(order)
        .limit(limit)
    ).all()
    return [(r[0], r[1]) for r in rows]


def index_batch(
    session: Session, client: QdrantClient, embedder: Embedder, batch: list[tuple[Article, Source]]
) -> IndexStats:
    stats = IndexStats()
    if not batch:
        return stats
    # 1. Article vectors for clustering: the article's own text, no outlet prefix (ADR-0016).
    art_vecs = embedder.encode([article_text(a.title, a.snippet) for a, _ in batch], sparse=False).dense
    upsert_article_vectors(
        client,
        [str(a.id) for a, _ in batch],
        art_vecs,
        [
            {
                "article_id": str(a.id),
                "source_id": str(s.id),
                "language": a.language,
                "published_at": iso(a.published_at),
                "is_syndicated": a.is_syndicated,
            }
            for a, s in batch
        ],
    )
    # 2. Chunks for retrieval: prefixed text is embedded; stored text is the raw chunk (docs/03).
    rows: list[tuple[Article, Source, int, TextChunk]] = []
    for a, s in batch:
        for idx, c in enumerate(chunk_article(a.title, a.snippet, a.full_text)):
            rows.append((a, s, idx, c))
    texts = [chunk_embed_text(s.name, a.published_at.date().isoformat(), a.title, c.text) for a, s, _, c in rows]
    enc = embedder.encode(texts, sparse=True)
    points = []
    for (a, s, idx, c), dense, sparse in zip(rows, enc.dense, enc.sparse, strict=True):
        point_id = str(uuid.uuid5(_NS, f"{a.id}:{idx}"))
        chunk_id = uuid.uuid5(_NS, f"chunk:{a.id}:{idx}")
        session.add(
            Chunk(
                id=chunk_id,
                article_id=a.id,
                idx=idx,
                text=c.text,
                char_start=c.start,
                char_end=c.end,
                token_count=len(c.text.split()),
                qdrant_point_id=uuid.UUID(point_id),
            )
        )
        points.append(
            ChunkPoint(
                point_id,
                dense,
                sparse,
                {
                    "chunk_id": str(chunk_id),
                    "article_id": str(a.id),
                    "story_id": None,
                    "source_id": str(s.id),
                    "language": a.language,
                    "published_at": iso(a.published_at),
                    "is_syndicated": a.is_syndicated,
                    "char_start": c.start,
                    "char_end": c.end,
                },
            )
        )
    upsert_chunks(client, points)
    stats.articles, stats.chunks = len(batch), len(points)
    return stats


def index_pending(limit: int = 10_000, batch_size: int = 64) -> IndexStats:
    client, embedder = get_qdrant(), get_embedder()
    ensure_collections(client, dim=embedder.dim)
    total = IndexStats()
    with Session(get_engine()) as session:
        while total.articles < limit:
            batch = unindexed(session, min(batch_size, limit - total.articles))
            if not batch:
                break
            st = index_batch(session, client, embedder, batch)
            session.commit()
            total.articles += st.articles
            total.chunks += st.chunks
            log.info("pipeline.index", articles=total.articles, chunks=total.chunks)
    return total


if __name__ == "__main__":
    configure_logging("INFO", json=False)
    s = index_pending()
    print(f"indexed {s.articles} articles, {s.chunks} chunks")
    sys.exit(0)
