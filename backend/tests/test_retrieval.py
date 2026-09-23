"""Retrieval building blocks: MaxSim, BM25 (Indic tokens), tier-1 grouping, source balancing, and
hybrid RRF search against an in-memory Qdrant with the test embedder."""

from datetime import UTC, datetime, timedelta
from typing import Any

import numpy as np
from qdrant_client import QdrantClient

from lens.core.config_files import load_yaml
from lens.nlp.embed import HashEmbedder
from lens.retrieval import balance
from lens.retrieval.qdrant_store import ChunkPoint, ensure_collections, iso, upsert_chunks
from lens.retrieval.search import BM25, Hit, chunk_filter, encode_query, hybrid, maxsim, stories_from_chunks

NOW = datetime(2026, 9, 23, 12, 0, tzinfo=UTC)
CFG: dict[str, Any] = load_yaml("retrieval.yaml")["balance"]


def _h(i: int, source: str, lang: str = "en", syn: bool = False, story: str = "s1") -> Hit:
    return Hit(f"c{i}", f"a{i}", story, source, lang, syn, 1.0 / (i + 1))


def test_maxsim_sums_each_query_tokens_best_match() -> None:
    q = np.array([[1.0, 0.0], [0.0, 1.0]])
    d = np.array([[1.0, 0.0], [0.6, 0.8]])
    assert maxsim(q, d) == 1.0 + 0.8


def test_bm25_ranks_by_rare_terms_and_handles_devanagari() -> None:
    idx = BM25({"a": "Rajya Sabha polls on October 16", "b": "राज्यसभा चुनाव 16 अक्टूबर को", "c": "Bank strike October 28"})
    assert idx.search("राज्यसभा चुनाव", 3)[0][0] == "b"
    assert idx.search("bank strike", 3)[0][0] == "c"
    assert idx.search("nothing matches", 3) == []


def test_tier1_groups_chunk_hits_by_story_in_rank_order() -> None:
    hits = [_h(0, "x", story="s2"), _h(1, "y", story="s1"), _h(2, "z", story="s2"), _h(3, "w", story="s3")]
    assert stories_from_chunks(hits, 2) == ["s2", "s1"]


def test_balance_round_robins_sources_with_a_cap_and_drops_copies() -> None:
    hits = [_h(0, "A"), _h(1, "A"), _h(2, "A"), _h(3, "B"), _h(4, "C", syn=True)]
    picked = balance.select(hits, {}, {**CFG, "ensure_language_groups": False, "ensure_bias_buckets": False})
    assert [h.chunk_id for h in picked] == ["c0", "c3", "c1"]  # A's third chunk capped (2), C is a copy


def test_balance_forces_in_missing_language_and_bias_groups() -> None:
    hits = [_h(i, f"en{i}") for i in range(12)] + [_h(20, "hi1", lang="hi")]
    bias = {f"en{i}": "right" for i in range(12)} | {"en11": "left"}
    picked = balance.select(hits, bias, {**CFG, "max_chunks": 5})
    assert len(picked) == 5
    assert any(h.language == "hi" for h in picked)  # Indian-language group present
    assert any(bias.get(h.source_id) == "left" for h in picked)  # left bucket present
    assert picked[0].chunk_id == "c0"  # the best chunk is kept


def test_hybrid_rrf_search_with_filters() -> None:
    client = QdrantClient(":memory:")
    emb = HashEmbedder()
    ensure_collections(client, dim=emb.dim, colbert_dim=emb.dim)
    texts = {
        "c1": ("Rajya Sabha polls on October 16 in Uttar Pradesh", "s1", NOW),
        "c2": ("Bank strike from September 28 to 30", "s2", NOW),
        "c3": ("Rajya Sabha polls old coverage", "s1", NOW - timedelta(days=90)),
    }
    enc = emb.encode([t for t, _, _ in texts.values()])
    upsert_chunks(
        client,
        [
            ChunkPoint(
                f"00000000-0000-0000-0000-00000000000{i}",
                enc.dense[i - 1],
                enc.sparse[i - 1],
                {
                    "chunk_id": f"c{i}",
                    "article_id": f"a{i}",
                    "story_id": story,
                    "source_id": f"src{i}",
                    "language": "en",
                    "published_at": iso(when),
                    "is_syndicated": False,
                },
            )
            for i, (text, story, when) in enumerate(texts.values(), 1)
        ],
    )
    q = encode_query(emb, "Rajya Sabha polls", colbert=False)
    hits = hybrid(client, q, chunk_filter(NOW, 30), dense_limit=10, sparse_limit=10, limit=5, rrf_k=60)
    assert hits and hits[0].article_id == "a1"
    assert "a3" not in {h.article_id for h in hits}  # outside the 30-day window
    only_s2 = hybrid(
        client, q, chunk_filter(NOW, 30, story_ids=["s2"]), dense_limit=10, sparse_limit=10, limit=5, rrf_k=60
    )
    assert {h.story_id for h in only_s2} == {"s2"}


def test_ablation_metrics() -> None:
    from lens.evals.retrieval_run import auc, best_threshold, story_metrics

    m = story_metrics(["x", "s1", "y"], {"s1"})
    assert m["recall@1"] == 0 and m["recall@5"] == 1 and m["mrr@10"] == 0.5
    assert abs(m["ndcg@10"] - 1 / np.log2(3)) < 1e-9
    assert auc([0.9, 0.8], [0.1, 0.8]) == 0.875
    assert best_threshold([0.9, 0.8], [0.1, 0.2]) == (0.8, 1.0, 0.0)
