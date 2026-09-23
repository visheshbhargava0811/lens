"""Retrieval ablation (docs/05, Phase 5): every variant on the same queries and story-level relevance.

Variants: BM25, dense, sparse, hybrid RRF (k=2 Qdrant default, k=config), hybrid + ColBERT MaxSim,
and tier 1 over story centroids. Reports Recall@k, MRR@10, nDCG@10 per variant,
by query type and language, latency p50/p95, storage per 1k chunks, no-answer separability of each
variant's top score, and per-outlet coverage of the evidence set with and without source balancing.

Relevance is story-level (a chunk is relevant when its story is), which is what the labels carry.

Usage: uv run --extra ml python -m lens.evals.retrieval_run [--queries FILE] [--name v1]
Writes reports/retrieval_ablation_<name>.md and .json.
"""

from __future__ import annotations

import argparse
import json
import math
import time
from collections import Counter, defaultdict
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
from qdrant_client import QdrantClient
from sqlalchemy import select as sql_select

from lens.core.config_files import load_yaml
from lens.core.settings import REPO_ROOT
from lens.db.models import Article, Chunk, Source
from lens.db.session import get_engine
from lens.nlp.embed import chunk_embed_text, get_embedder
from lens.pipeline.stats import best_ratings
from lens.retrieval import balance
from lens.retrieval.qdrant_store import CHUNKS, get_qdrant
from lens.retrieval.search import (
    BM25,
    EncodedQuery,
    Hit,
    chunk_filter,
    dense,
    encode_query,
    hybrid,
    maxsim,
    sparse,
    stories_dense,
    stories_from_chunks,
)
from lens.stats.coverage import BIAS_BUCKETS, bucket

KS = (1, 5, 10)
TYPES = ("entity", "paraphrase", "cross_lingual", "hinglish", "loaded")


# ------------------------------------------------------------------ metrics (pure)


def story_metrics(ranked: Sequence[str], relevant: set[str]) -> dict[str, float]:
    """Binary story relevance: Recall@k, reciprocal rank within 10, nDCG@10."""
    out = {f"recall@{k}": len(relevant & set(ranked[:k])) / len(relevant) for k in KS}
    out["mrr@10"] = next((1 / (i + 1) for i, s in enumerate(ranked[:10]) if s in relevant), 0.0)
    dcg = sum(1 / math.log2(i + 2) for i, s in enumerate(ranked[:10]) if s in relevant)
    idcg = sum(1 / math.log2(i + 2) for i in range(min(len(relevant), 10)))
    out["ndcg@10"] = dcg / idcg
    return out


def auc(pos: Sequence[float], neg: Sequence[float]) -> float | None:
    """P(score of an answerable query > score of a no-answer query); ties count half."""
    if not pos or not neg:
        return None
    wins = sum((p > n) + 0.5 * (p == n) for p in pos for n in neg)
    return wins / (len(pos) * len(neg))


def best_threshold(pos: Sequence[float], neg: Sequence[float]) -> tuple[float, float, float]:
    """Youden's J over observed scores: (threshold, share of answerable kept, share of no-answer kept)."""
    best = (0.0, 1.0, 1.0, -1.0)
    for t in sorted(set(pos) | set(neg)):
        tpr = sum(p >= t for p in pos) / len(pos)
        fpr = sum(n >= t for n in neg) / len(neg)
        if tpr - fpr > best[3]:
            best = (t, tpr, fpr, tpr - fpr)
    return best[:3]


def pct(xs: Sequence[float], p: float) -> float:
    return float(np.percentile(xs, p)) if xs else 0.0


def evidence_coverage(picked: Sequence[Hit], bias_of: dict[str, str], pool: Sequence[Hit]) -> dict[str, float]:
    """How broad an evidence set is, relative to what the candidate pool could have offered."""

    def lang(h: Hit) -> str:
        return "en" if h.language.split("-")[0] == "en" else "indic"

    per_src = Counter(h.source_id for h in picked)
    avail_bias = {bias_of.get(h.source_id, "unrated") for h in pool}
    avail_lang = {lang(h) for h in pool}
    return {
        "outlets": len(per_src),
        "outlets_available": len({h.source_id for h in pool}),
        "max_outlet_share": max(per_src.values()) / len(picked) if picked else 0.0,
        "bias_buckets_covered": len({bias_of.get(h.source_id, "unrated") for h in picked} & avail_bias)
        / len(avail_bias)
        if avail_bias
        else 0.0,
        "language_groups_covered": len({lang(h) for h in picked} & avail_lang) / len(avail_lang) if avail_lang else 0.0,
        "syndicated_copies": sum(h.is_syndicated for h in picked),
    }


# ------------------------------------------------------------------ corpus


def load_corpus() -> tuple[dict[str, str], dict[str, Hit], dict[str, str]]:
    """Chunk embed texts and Hit rows keyed by chunk_id, and source_id -> outlet bias bucket."""
    from sqlalchemy.orm import Session

    value_map = load_yaml("guardrails.yaml")["stats"]["bias_value_map"]
    texts: dict[str, str] = {}
    hits: dict[str, Hit] = {}
    with Session(get_engine()) as s:
        rows = s.execute(
            sql_select(Chunk, Article, Source).join(Article, Chunk.article_id == Article.id).join(Source)
        ).all()
        for c, a, src in rows:
            cid = str(c.id)
            texts[cid] = chunk_embed_text(src.name, a.published_at.date().isoformat(), a.title, c.text)
            hits[cid] = Hit(cid, str(a.id), None, str(src.id), a.language, a.is_syndicated, 0.0)
        ratings = best_ratings(s, "bias")
    bias_of = {str(sid): bucket(r.value, value_map, BIAS_BUCKETS) for sid, r in ratings.items()}
    return texts, hits, bias_of


def attach_story_ids(client: QdrantClient, hits: dict[str, Hit]) -> None:
    """BM25 hits come from Postgres; story_id lives on the Qdrant payload (written by clustering)."""
    offset = None
    while True:
        pts, offset = client.scroll(
            CHUNKS, limit=5000, offset=offset, with_payload=["chunk_id", "story_id"], with_vectors=False
        )
        for p in pts:
            pl = p.payload or {}
            h = hits.get(str(pl.get("chunk_id")))
            if h is not None:
                hits[h.chunk_id] = Hit(**{**h.__dict__, "story_id": pl.get("story_id")})
        if offset is None:
            return


def storage_per_1k(client: QdrantClient, colbert_tokens: Sequence[int]) -> dict[str, float]:
    """Raw vector bytes per 1,000 chunks (index overhead excluded)."""
    pts, _ = client.scroll(CHUNKS, limit=1000, with_vectors=["sparse"], with_payload=False)
    nnz = [len(p.vector["sparse"].indices) for p in pts if isinstance(p.vector, dict) and "sparse" in p.vector]  # type: ignore[union-attr]
    avg_tok = float(np.mean(colbert_tokens)) if colbert_tokens else 0.0
    mb = 1000 / 1e6
    return {
        "dense_f32_mb": 1024 * 4 * mb,
        "sparse_mb": float(np.mean(nnz)) * 8 * mb if nnz else 0.0,
        "sparse_avg_nnz": float(np.mean(nnz)) if nnz else 0.0,
        "colbert_avg_tokens": avg_tok,
        "colbert_f32_mb": avg_tok * 1024 * 4 * mb,
        "colbert_f16_mb": avg_tok * 1024 * 2 * mb,
        "colbert_uint8_mb": avg_tok * 1024 * 1 * mb,
    }


# ------------------------------------------------------------------ rerankers


class ColbertReranker:
    """Query-time MaxSim: candidate token vectors encoded per query (nothing stored)."""

    def __init__(self, embedder: Any) -> None:
        self.embedder = embedder
        self.token_counts: list[int] = []

    def __call__(self, q: EncodedQuery, cands: Sequence[Hit], texts: dict[str, str], top_k: int) -> list[Hit]:
        assert q.colbert is not None
        cands = [h for h in cands if h.chunk_id in texts]  # chunks indexed after the corpus snapshot are skipped
        enc = self.embedder.encode([texts[h.chunk_id] for h in cands], sparse=False, colbert=True)
        self.token_counts.extend(len(v) for v in enc.colbert)
        # Normalize by query length so the top score is comparable across queries (no-answer check).
        scored = [(maxsim(q.colbert, v) / len(q.colbert), h) for h, v in zip(cands, enc.colbert, strict=True)]
        scored.sort(key=lambda t: -t[0])
        return [Hit(**{**h.__dict__, "score": s}) for s, h in scored[:top_k]]


# ------------------------------------------------------------------ run


def run(queries: list[dict[str, Any]]) -> dict[str, Any]:
    cfg = load_yaml("retrieval.yaml")
    t1, t2, bal = cfg["tier1"], cfg["tier2"], cfg["balance"]
    client, embedder = get_qdrant(), get_embedder()
    texts, corpus_hits, bias_of = load_corpus()
    attach_story_ids(client, corpus_hits)
    bm25 = BM25(texts)
    colbert = ColbertReranker(embedder)
    now = datetime.now(UTC)
    flt = chunk_filter(now, t1["window_days"])
    n_cand = t2["fused_limit"]

    def bm25_hits(text: str) -> list[Hit]:
        return [corpus_hits[c] for c, _ in bm25.search(text, n_cand) if c in corpus_hits]

    per_query: list[dict[str, Any]] = []
    latency: dict[str, list[float]] = defaultdict(list)
    for i, row in enumerate(queries):
        text = row["inputs"]["query"]
        relevant = set(row["reference_outputs"]["relevant_story_ids"])
        t0 = time.perf_counter()
        q = encode_query(embedder, text, colbert=True)
        latency["encode_query"].append((time.perf_counter() - t0) * 1000)

        def timed(name: str, fn: Callable[..., list[Hit]], *args: Any, base: str | None = None, **kw: Any) -> list[Hit]:
            t = time.perf_counter()
            out = fn(*args, **kw)
            ms = (time.perf_counter() - t) * 1000 + (latency[base][-1] if base else 0.0)
            latency[name].append(ms)
            return out

        lim = {"dense_limit": t2["dense_limit"], "sparse_limit": t2["sparse_limit"], "limit": n_cand}
        hk = f"hybrid_rrf_k{t2['rrf_k']}"
        runs: dict[str, list[Hit]] = {
            "bm25": timed("bm25", bm25_hits, text),
            "dense": timed("dense", dense, client, q, flt, n_cand),
            "sparse": timed("sparse", sparse, client, q, flt, n_cand),
            "hybrid_rrf_k2": timed("hybrid_rrf_k2", hybrid, client, q, flt, rrf_k=2, **lim),
            hk: timed(hk, hybrid, client, q, flt, rrf_k=t2["rrf_k"], **lim),
        }
        top_k = t2["rerank_top_k"]
        runs[f"{hk}+colbert"] = timed(f"{hk}+colbert", colbert, q, runs[hk], texts, top_k, base=hk)
        t = time.perf_counter()
        tier1 = stories_dense(client, q, now, t1["window_days"], 10)
        latency["tier1_stories_dense"].append((time.perf_counter() - t) * 1000)

        rec: dict[str, Any] = {"id": row["id"], "type": row["tags"]["type"], "lang": row["tags"]["language"]}
        rec["top_score"] = {name: (hits[0].score if hits else 0.0) for name, hits in runs.items()}
        rec["top_score"]["tier1_stories_dense"] = tier1[0][1] if tier1 else 0.0
        if relevant:
            rec["metrics"] = {
                name: story_metrics(stories_from_chunks(hits, 10), relevant) for name, hits in runs.items()
            }
            rec["metrics"]["tier1_stories_dense"] = story_metrics([s for s, _ in tier1], relevant)
            rec["metrics"][f"tier1_from_{hk}"] = rec["metrics"][hk]  # same ranking, named for the tier-1 table
            # Evidence set: tier 2 hybrid inside the correct stories (top rerank_top_k), plain top-N vs balanced.
            # Hybrid order, not ColBERT: balancing is reranker-independent and a second rerank doubles runtime.
            pool = hybrid(
                client,
                q,
                chunk_filter(now, t1["window_days"], story_ids=sorted(relevant)),
                dense_limit=t2["dense_limit"],
                sparse_limit=t2["sparse_limit"],
                limit=n_cand,
                rrf_k=t2["rrf_k"],
            )
            if pool:
                reranked = pool[: t2["rerank_top_k"]]
                t = time.perf_counter()
                balanced = balance.select(reranked, bias_of, bal)
                latency["balance"].append((time.perf_counter() - t) * 1000)
                rec["coverage"] = {
                    "plain": evidence_coverage(reranked[: bal["max_chunks"]], bias_of, pool),
                    "balanced": evidence_coverage(balanced, bias_of, pool),
                }
        per_query.append(rec)
        if (i + 1) % 20 == 0:
            print(f"{i + 1}/{len(queries)}", flush=True)

    return {
        "per_query": per_query,
        "latency": latency,
        "storage": storage_per_1k(client, colbert.token_counts),
        "config": cfg,
    }


def summarize(res: dict[str, Any]) -> dict[str, Any]:
    ans = [r for r in res["per_query"] if "metrics" in r]
    noans = [r for r in res["per_query"] if "metrics" not in r]
    variants = list(ans[0]["metrics"]) if ans else []

    def mean(rows: list[dict[str, Any]], v: str, m: str) -> float:
        return float(np.mean([r["metrics"][v][m] for r in rows])) if rows else 0.0

    metric_names = [*(f"recall@{k}" for k in KS), "mrr@10", "ndcg@10"]
    overall = {v: {m: mean(ans, v, m) for m in metric_names} for v in variants}
    by_type = {v: {t: mean([r for r in ans if r["type"] == t], v, "recall@5") for t in TYPES} for v in variants}
    langs = sorted({r["lang"] for r in ans})
    by_lang = {v: {lg: mean([r for r in ans if r["lang"] == lg], v, "recall@5") for lg in langs} for v in variants}
    sep = {}
    for v in res["per_query"][0]["top_score"]:
        pos = [r["top_score"][v] for r in ans]
        neg = [r["top_score"][v] for r in noans]
        a = auc(pos, neg)
        thr = best_threshold(pos, neg) if a is not None else None
        sep[v] = {"auc": a, "threshold": thr}
    cov_rows = [r["coverage"] for r in ans if "coverage" in r]
    coverage = (
        {
            mode: {k: float(np.mean([c[mode][k] for c in cov_rows])) for k in cov_rows[0][mode]}
            for mode in ("plain", "balanced")
        }
        if cov_rows
        else {}
    )
    lat = {k: {"p50": pct(v, 50), "p95": pct(v, 95)} for k, v in res["latency"].items()}
    counts = {
        "answerable": len(ans),
        "no_answer": len(noans),
        "types": dict(Counter(r["type"] for r in ans)),
        "langs": dict(Counter(r["lang"] for r in ans)),
    }
    min_score = res["config"]["tier1"]["min_score"]
    t1_pos = [r["top_score"]["tier1_stories_dense"] for r in ans]
    t1_neg = [r["top_score"]["tier1_stories_dense"] for r in noans]
    min_score_check = {
        "min_score": min_score,
        "answerable_kept": sum(s >= min_score for s in t1_pos) / len(t1_pos) if t1_pos else None,
        "no_answer_kept": sum(s >= min_score for s in t1_neg) / len(t1_neg) if t1_neg else None,
    }
    return {
        "counts": counts,
        "overall": overall,
        "recall5_by_type": by_type,
        "recall5_by_lang": by_lang,
        "no_answer": sep,
        "min_score_check": min_score_check,
        "coverage": coverage,
        "coverage_n": len(cov_rows),
        "max_chunks": res["config"]["balance"]["max_chunks"],
        "latency_ms": lat,
        "storage_per_1k_chunks": res["storage"],
    }


def render(s: dict[str, Any], queries_path: str) -> str:
    f = "{:.3f}".format
    L = [
        "# Retrieval ablation run",
        "",
        f"Queries: `{queries_path}`. Answerable {s['counts']['answerable']}, no-answer {s['counts']['no_answer']}.",
        f"Types: {s['counts']['types']}. Languages: {s['counts']['langs']}.",
        "Relevance is story-level. Cross-encoder rerank dropped before measurement (owner decision, ADR).",
        "",
        "## Story retrieval",
        "",
        "| Variant | R@1 | R@5 | R@10 | MRR@10 | nDCG@10 |",
        "|---|---|---|---|---|---|",
    ]
    for v, m in s["overall"].items():
        L.append(
            f"| {v} | " + " | ".join(f(m[k]) for k in ("recall@1", "recall@5", "recall@10", "mrr@10", "ndcg@10")) + " |"
        )
    for title, key in (
        ("Recall@5 by query type", "recall5_by_type"),
        ("Recall@5 by query language", "recall5_by_lang"),
    ):
        cols = list(next(iter(s[key].values())))
        L += ["", f"## {title}", "", "| Variant | " + " | ".join(cols) + " |", "|---" * (len(cols) + 1) + "|"]
        for v, row in s[key].items():
            L.append(f"| {v} | " + " | ".join(f(row[c]) for c in cols) + " |")
    L += [
        "",
        "## No-answer separability (top score, answerable vs no-answer)",
        "",
        "| Variant | AUC | Best threshold | Answerable kept | No-answer kept |",
        "|---|---|---|---|---|",
    ]
    for v, x in s["no_answer"].items():
        if x["auc"] is None:
            continue
        t, tpr, fpr = x["threshold"]
        L.append(f"| {v} | {f(x['auc'])} | {f(t)} | {f(tpr)} | {f(fpr)} |")
    m = s["min_score_check"]
    L += [
        "",
        f"Current `tier1.min_score` {m['min_score']} on story cosine keeps {m['answerable_kept']} of answerable"
        f" and {m['no_answer_kept']} of no-answer queries.",
    ]
    if s["coverage"]:
        L += [
            "",
            f"## Evidence coverage, top {s['max_chunks']} chunks in the relevant stories (n={s['coverage_n']})",
            "",
            "| Metric | Plain top-k | Source-balanced |",
            "|---|---|---|",
        ]
        for k in s["coverage"]["plain"]:
            L.append(f"| {k} | {f(s['coverage']['plain'][k])} | {f(s['coverage']['balanced'][k])} |")
    L += [
        "",
        "## Latency (ms, local, excludes shared query encoding unless named)",
        "",
        "| Stage | p50 | p95 |",
        "|---|---|---|",
    ]
    for k, v in s["latency_ms"].items():
        L.append(f"| {k} | {v['p50']:.1f} | {v['p95']:.1f} |")
    L += ["", "## Storage per 1,000 chunks (raw vectors, MB)", "", "| Item | Value |", "|---|---|"]
    for k, v in s["storage_per_1k_chunks"].items():
        L.append(f"| {k} | {v:.2f} |")
    return "\n".join(L) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--queries", default="data/evals/retrieval/queries_v1.jsonl")
    ap.add_argument("--name", default="v1")
    args = ap.parse_args()
    path = REPO_ROOT / args.queries
    queries = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    res = run(queries)
    summary = summarize(res)
    out = REPO_ROOT / "reports" / f"retrieval_ablation_{args.name}"
    Path(f"{out}.json").write_text(
        json.dumps({"summary": summary, "per_query": res["per_query"]}, indent=1, default=str)
    )
    Path(f"{out}.md").write_text(render(summary, args.queries))
    print(render(summary, args.queries))


if __name__ == "__main__":
    main()
