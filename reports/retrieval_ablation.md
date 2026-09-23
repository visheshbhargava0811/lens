# Retrieval ablation (Phase 5)

Run: 2026-09-23, `make eval-retrieval` → full tables in [`retrieval_ablation_v1.md`](retrieval_ablation_v1.md), per-query data in `retrieval_ablation_v1.json`.

Query set: `data/evals/retrieval/queries_v1.jsonl`, 172 queries (157 answerable, 15 no-answer) drafted by Claude from 119 real stories. The owner checked `to_review_v1.csv` and accepted it as is on 2026-09-23 with no corrections, so these results are on the accepted set. Relevance is story-level: one labelled story per query. Re-running needs no re-index: every vector type stays stored.

Corpus: 32,484 chunks from 5 days (18–23 Sep 2026), `snippet_only` licensing. Hardware: Apple Silicon (MPS), with the pipeline worker running alongside, so latencies are indicative.

## Results

| Variant | R@1 | R@5 | MRR@10 | nDCG@10 | Search p50 / p95 ms |
|---|---|---|---|---|---|
| BM25 (floor) | 0.495 | 0.659 | 0.588 | 0.598 | 5 / 48 |
| Sparse (BGE-M3) | 0.479 | 0.618 | 0.564 | 0.585 | 7 / 13 |
| **Dense (BGE-M3)** | **0.806** | **0.951** | **0.901** | **0.905** | 15 / 28 |
| Hybrid RRF, k=2 (Qdrant default) | 0.591 | 0.935 | 0.768 | 0.807 | 10 / 17 |
| Hybrid RRF, k=60 (docs/05) | 0.581 | 0.761 | 0.691 | 0.730 | 10 / 16 |
| Hybrid k=60 + ColBERT (query-time) | 0.766 | 0.951 | 0.873 | 0.884 | 9,891 / 13,665 |
| Tier 1: story centroids, dense | 0.793 | 0.951 | 0.887 | 0.900 | 13 / 22 |
| Hybrid + cross-encoder | not run: dropped before measurement (ADR-0028) | | | | |
| Recursive vs semantic chunking | N/A: every article is exactly one chunk under `snippet_only` (max chunks per article = 1 across 32,484) | | | | |

Query encoding (one BGE-M3 pass) adds p50 80 ms / p95 155 ms to every variant except BM25.

Recall@5 by type (dense / hybrid k=60 / sparse): entity 0.988 / 0.988 / 0.963, paraphrase 0.959 / 0.929 / 0.724, cross-lingual **0.986 / 0.338 / 0.135**, Hinglish 0.900 / 0.700 / 0.550, loaded 0.725 / 0.700 / 0.600.

Per query (Recall@5): sparse finds the story when dense misses in **1 of 157** (a loaded query, which query neutralization is meant to fix). Hybrid (either k) and ColBERT never beat dense. Dense beats hybrid k=2 on 3 queries (cross-lingual and loaded).

**Why hybrid loses here.** Sparse is lexical, so a Hindi query against English coverage (and the reverse) scores near zero. RRF then mixes that noise into the ranking with equal weight. A larger k flattens the ranks further, which is why k=60 is worse than k=2. Entity queries, where sparse should win, are already at 0.988 with dense, because chunk text carries the headline.

## No-answer (abstain) separability

AUC of the top score, answerable vs no-answer (n = 157 / 15):

| Score | AUC | Threshold (Youden) | Answerable kept | No-answer kept |
|---|---|---|---|---|
| Tier 1 story cosine | **0.930** | 0.664 | 0.841 | 0.000 |
| Dense chunk cosine | 0.923 | 0.582 | 0.904 | 0.133 |
| ColBERT MaxSim / query tokens | 0.864 | 0.633 | 0.796 | 0.133 |
| Hybrid RRF | 0.61 | n/a | n/a | n/a |

The docs/05 starting value `tier1.min_score: 0.35` keeps 100% of the no-answer queries, so it never abstains. RRF scores are rank-based and useless for abstaining.

## Storage per 1,000 chunks (raw vectors)

| Vector | MB |
|---|---|
| Dense, 1024 × f32 | 4.10 |
| Sparse (avg 33 non-zeros) | 0.27 |
| ColBERT multivector, avg 87 tokens × 1024: f32 / f16 / uint8 | 354.8 / 177.4 / 88.7 |

At today's corpus, stored ColBERT vectors would be about 11.5 GB (f32), roughly 87× the dense vectors. The earlier 21-token estimate counted raw snippet words; the embedded text also carries the outlet, date and headline prefix.

## Source balancing

Evidence set: top 12 chunks from tier 2 inside the relevant stories, plain top-k vs `balance.select` (157 queries):

| Metric (mean per query) | Plain top-k | Balanced |
|---|---|---|
| Distinct outlets (of 4.93 available) | 4.50 | **4.65** |
| Largest single-outlet share | 0.323 | **0.296** |
| Language groups covered (EN / Indic) | 0.981 | **0.997** |
| Bias buckets covered | 0.987 | 0.988 |
| Syndicated copies in the set | 0.134 | **0** |

Balancing improves every coverage measure at about 0.05 ms. Gains are small because the typical story has only about 5 outlets, and plain top-12 already reaches most of them. The gain should grow for large stories and for Ask queries that span several stories.

## Decisions (ADR-0029)

| Component | Decision | Why |
|---|---|---|
| Dense chunk search (tier 2) | **Keep: default** | Best on every metric and type; 15 ms |
| Sparse search + RRF fusion | **Drop from the query path**; keep sparse vectors stored | One win in 157; fusion costs 22 R@1 points; storage is 0.27 MB/1k, so a future query set can re-test it without re-indexing |
| ColBERT rerank | **Drop**; do not store multivectors | No gain over dense, 10 s query-time or about 355 MB/1k stored |
| Cross-encoder rerank | Dropped (ADR-0028) | Latency |
| Tier 1 over story centroids (dense) | **Keep** | Matches dense chunks (1 win each way) and gives the best abstain signal |
| `tier1.min_score` | **0.35 → 0.66** | 0.35 never abstains; 0.66 keeps 84% of answerable and 0% of no-answer on 15 no-answer queries. Re-tune when more no-answer queries exist |
| Source-balanced selection | **Keep** | Improves outlet spread, language coverage and syndication at no cost |
| Chunking strategy | N/A | One chunk per article under `snippet_only`; revisit only for `full_text` sources |

## Limits

- The queries were drafted by Claude, and the owner accepted them without row-level corrections. They may lean toward headline wording; a second, independently written set would test that.
- There are only 15 no-answer queries, so the threshold is a starting point.
- Marathi has n=5.
- Latency was measured locally on MPS, sharing the machine with the pipeline worker.
