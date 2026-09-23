# 05 Retrieval

Stack: **semantic chunks, hybrid dense + sparse search fused with RRF, ColBERT late-interaction rerank, source-balanced evidence selection.**

Add each component only if evals show it earns its latency and storage cost (ablation plan below).

> **Phase 5 result (ADR-0029, provisional until the reviewed query set):** the ablation kept **dense** search, tier 1 over story centroids, and source balancing. Sparse + RRF and ColBERT rerank did not earn their cost on this corpus and are off by default (`tier2.mode`, `tier2.rerank`). The flow below is the original design; see `reports/retrieval_ablation.md`.

## Flow

```
Query (neutralized)
  -> encode once with BGE-M3: dense, sparse, colbert token vectors
  -> Tier 1: find stories   (Qdrant `stories`: dense + sparse, RRF, time filter)
  -> Tier 2: find chunks    (Qdrant `chunks` filtered by story_id(s))
        prefetch dense top 50 + sparse top 50 -> RRF -> top 100
        ColBERT MaxSim rerank -> top 20
  -> Source-balanced selection -> evidence set (<= 12 chunks)
  -> Evidence guard (docs/07)
```

If Tier 1 finds nothing above threshold, fall back to a global chunk search (no story filter, time window applied). If that is also weak, trigger the Freshness node once, then abstain.

## Models

- **BGE-M3** produces all three representations from one pass. Default for dense, sparse, and multivector.
- **Jina-ColBERT-v2** is an alternative multilingual ColBERT to benchmark for the rerank stage.
- Original ColBERTv2 is English-only. Do not use it for Hindi or regional languages.
- Optional cross-encoder rerank (for example a multilingual bge-reranker) as a comparison in the ablation.
- Model cards do not prove Indic quality. Measure on `data/evals/retrieval/`.

## Why hybrid for news

Dense handles paraphrase and cross-lingual matches. Sparse handles names, acronyms, article numbers, bill names, place names. Fuse with Reciprocal Rank Fusion, which needs no score calibration.

## Reference implementation (verify against current Qdrant docs before use)

```python
from qdrant_client import QdrantClient, models

def retrieve_chunks(client: QdrantClient, q, flt: models.Filter, top_k: int = 20):
    return client.query_points(
        "chunks",
        prefetch=models.Prefetch(
            prefetch=[
                models.Prefetch(query=q.dense, using="dense", limit=50, filter=flt),
                models.Prefetch(
                    query=models.SparseVector(indices=q.sparse_idx, values=q.sparse_val),
                    using="sparse", limit=50, filter=flt),
            ],
            query=models.RrfQuery(rrf=models.Rrf(k=60)),  # verified 2026-09-23: replaces FusionQuery; Qdrant's default k is 2
            limit=100,
        ),
        query=q.colbert,          # list of token vectors
        using="colbert",
        limit=top_k,
        with_payload=True,
    ).points
```

Filters: time window (default 30 days, widened on retry), `story_id in [...]`, optional `language`, always `is_syndicated = false` unless collapsing explicitly.

## Config: `config/retrieval.yaml`

```yaml
tier1:
  window_days: 30
  top_stories: 3
  min_score: 0.35            # tune
tier2:
  dense_limit: 50
  sparse_limit: 50
  fused_limit: 100
  rrf_k: 60
  rerank_top_k: 20
  rerank: colbert            # colbert | cross_encoder | none
balance:
  max_chunks: 12
  per_source_cap: 2
  ensure_bias_buckets: true     # outlet Left / Center / Right / unrated (ADR-0020)
  ensure_language_groups: true
  collapse_syndicated: true
retry:
  max_attempts: 2
  widen_window_days: [30, 90]
freshness:
  enabled: true
  timeout_s: 8
  max_articles: 20
```

## Source-balanced evidence selection

A plain top-k often returns many chunks from two outlets, which destroys a coverage comparison. After reranking:

1. **Collapse syndicated copies:** keep the original, record `also_carried_by`.
2. **Round-robin by source:** take the best remaining chunk from each source in rank order until `max_chunks`, with `per_source_cap`.
3. **Ensure diversity:** if the candidates include a bias bucket (ADR-0020) or language group that the selection lacks, force-include the top chunk from each missing group.
4. **Keep provenance:** every selected chunk keeps `article_id`, `source_id`, `stance`, `language`, `published_at`, offsets.
5. **Never let personalization change this selection.** Memory may influence output language and format only.

```python
def select_evidence(reranked, story_stats, cfg):
    pool = collapse_syndicated(reranked)
    picked, per_source = [], Counter()
    for chunk in round_robin_by_source(pool):
        if per_source[chunk.source_id] >= cfg.per_source_cap:
            continue
        picked.append(chunk); per_source[chunk.source_id] += 1
        if len(picked) >= cfg.max_chunks:
            break
    picked = ensure_missing_groups(picked, pool, story_stats, cfg)
    return picked
```

## ColBERT storage strategy

Multivectors store one vector per token. At 1024 dimensions and about 150 tokens per chunk in float32, that is roughly 600 KB per chunk. Options, decide with measurements:

| Option | Trade-off |
|---|---|
| 128-d ColBERT model (Jina-ColBERT-v2 class) | Smaller, separate model to run |
| Float16 or quantized multivectors | Some quality risk, measure |
| Keep multivectors only for the last 30 to 60 days | News relevance decays fast. Older material falls back to hybrid only |
| Encode candidates at query time | No storage, more latency |

`hnsw_config.m = 0` on the multivector field since it is used for reranking only.

## Query encoding notes

- Encode once, reuse dense, sparse, and colbert outputs.
- Hinglish and romanized Hindi: keep the original text for sparse. Test whether dense handles it. If not, add a transliteration variant of the query and union the results.
- Neutralized query only. Never search with loaded phrasing from the raw query.

## Ablation plan (Phase 5 deliverable: `reports/retrieval_ablation.md`)

Run on the same query set and labeled relevance data:

| Variant | Purpose |
|---|---|
| BM25 only | Floor |
| Dense only | Baseline |
| Sparse only | Lexical contribution |
| Hybrid RRF | Fusion gain |
| Hybrid + ColBERT | Rerank gain |
| Hybrid + cross-encoder | Alternative rerank |
| Above + recursive chunking vs semantic chunking | Chunking gain |

Report Recall@k, MRR, nDCG, per-outlet coverage of top-k, p50 and p95 latency, storage per 1k chunks. Keep only components whose gain justifies cost. Record the decision in `docs/DECISIONS.md`.

## Retrieval eval data

`data/evals/retrieval/*.jsonl`: at least 150 queries in English, Hindi, and Hinglish, with labeled relevant stories and chunks. Include:
- Named-entity-heavy queries (sparse should win)
- Paraphrase and cross-lingual queries (dense should win)
- Loaded or false-premise queries (neutralization should help)
- Very recent events (freshness path)
- No-answer queries (abstain path)
