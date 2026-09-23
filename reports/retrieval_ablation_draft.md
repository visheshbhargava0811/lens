# Retrieval ablation run

Queries: `data/evals/retrieval/queries_v1.draft.jsonl`. Answerable 157, no-answer 15.
Types: {'entity': 41, 'paraphrase': 49, 'cross_lingual': 37, 'hinglish': 20, 'loaded': 10}. Languages: {'en': 109, 'hi': 23, 'hinglish': 20, 'mr': 5}.
Relevance is story-level. Cross-encoder rerank dropped before measurement (owner decision, ADR).

## Story retrieval

| Variant | R@1 | R@5 | R@10 | MRR@10 | nDCG@10 |
|---|---|---|---|---|---|
| bm25 | 0.495 | 0.659 | 0.678 | 0.588 | 0.598 |
| dense | 0.806 | 0.951 | 0.957 | 0.901 | 0.905 |
| sparse | 0.479 | 0.618 | 0.685 | 0.564 | 0.585 |
| hybrid_rrf_k2 | 0.591 | 0.935 | 0.959 | 0.768 | 0.807 |
| hybrid_rrf_k60 | 0.581 | 0.761 | 0.901 | 0.691 | 0.730 |
| hybrid_rrf_k60+colbert | 0.766 | 0.951 | 0.952 | 0.873 | 0.884 |
| tier1_stories_dense | 0.793 | 0.951 | 0.967 | 0.887 | 0.900 |
| tier1_from_hybrid_rrf_k60 | 0.581 | 0.761 | 0.901 | 0.691 | 0.730 |

## Recall@5 by query type

| Variant | entity | paraphrase | cross_lingual | hinglish | loaded |
|---|---|---|---|---|---|
| bm25 | 0.963 | 0.847 | 0.135 | 0.550 | 0.650 |
| dense | 0.988 | 0.959 | 0.986 | 0.900 | 0.725 |
| sparse | 0.963 | 0.724 | 0.135 | 0.550 | 0.600 |
| hybrid_rrf_k2 | 0.988 | 0.959 | 0.932 | 0.900 | 0.675 |
| hybrid_rrf_k60 | 0.988 | 0.929 | 0.338 | 0.700 | 0.700 |
| hybrid_rrf_k60+colbert | 0.988 | 0.959 | 0.986 | 0.900 | 0.725 |
| tier1_stories_dense | 0.988 | 0.959 | 0.986 | 0.900 | 0.725 |
| tier1_from_hybrid_rrf_k60 | 0.988 | 0.929 | 0.338 | 0.700 | 0.700 |

## Recall@5 by query language

| Variant | en | hi | hinglish | mr |
|---|---|---|---|---|
| bm25 | 0.702 | 0.500 | 0.550 | 0.900 |
| dense | 0.956 | 0.978 | 0.900 | 0.900 |
| sparse | 0.642 | 0.500 | 0.550 | 0.900 |
| hybrid_rrf_k2 | 0.943 | 0.935 | 0.900 | 0.900 |
| hybrid_rrf_k60 | 0.794 | 0.630 | 0.700 | 0.900 |
| hybrid_rrf_k60+colbert | 0.956 | 0.978 | 0.900 | 0.900 |
| tier1_stories_dense | 0.956 | 0.978 | 0.900 | 0.900 |
| tier1_from_hybrid_rrf_k60 | 0.794 | 0.630 | 0.700 | 0.900 |

## No-answer separability (top score, answerable vs no-answer)

| Variant | AUC | Best threshold | Answerable kept | No-answer kept |
|---|---|---|---|---|
| bm25 | 0.500 | 0.000 | 1.000 | 1.000 |
| dense | 0.923 | 0.582 | 0.904 | 0.133 |
| sparse | 0.724 | 0.185 | 0.573 | 0.133 |
| hybrid_rrf_k2 | 0.610 | 0.548 | 0.892 | 0.667 |
| hybrid_rrf_k60 | 0.616 | 0.031 | 0.847 | 0.600 |
| hybrid_rrf_k60+colbert | 0.864 | 0.633 | 0.796 | 0.133 |
| tier1_stories_dense | 0.930 | 0.664 | 0.841 | 0.000 |

Current `tier1.min_score` 0.35 on story cosine keeps 1.0 of answerable and 1.0 of no-answer queries.

## Evidence coverage, top 12 chunks in the relevant stories (n=157)

| Metric | Plain top-k | Source-balanced |
|---|---|---|
| outlets | 4.497 | 4.650 |
| outlets_available | 4.930 | 4.930 |
| max_outlet_share | 0.323 | 0.296 |
| bias_buckets_covered | 0.987 | 0.988 |
| language_groups_covered | 0.981 | 0.997 |
| syndicated_copies | 0.134 | 0.000 |

## Latency (ms, local, excludes shared query encoding unless named)

| Stage | p50 | p95 |
|---|---|---|
| encode_query | 80.2 | 155.1 |
| bm25 | 5.1 | 47.9 |
| dense | 14.7 | 28.3 |
| sparse | 6.5 | 12.6 |
| hybrid_rrf_k2 | 10.4 | 17.2 |
| hybrid_rrf_k60 | 10.2 | 16.1 |
| hybrid_rrf_k60+colbert | 9890.7 | 13664.9 |
| tier1_stories_dense | 12.9 | 21.9 |
| balance | 0.0 | 0.1 |

## Storage per 1,000 chunks (raw vectors, MB)

| Item | Value |
|---|---|
| dense_f32_mb | 4.10 |
| sparse_mb | 0.27 |
| sparse_avg_nnz | 33.42 |
| colbert_avg_tokens | 86.61 |
| colbert_f32_mb | 354.75 |
| colbert_f16_mb | 177.37 |
| colbert_uint8_mb | 88.69 |
