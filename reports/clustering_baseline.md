# Clustering eval: baseline

Generated 2026-09-23 01:25 UTC. Gold: 436 articles, 211 stories. Raw numbers: `reports/clustering_baseline.json`.

| Run | Split | bcubed_precision | bcubed_recall | bcubed_f1 | ari | v_measure | merge_error_rate | hard_negative_merges | verifier_call_rate | cross-lingual recall | cross-lingual precision |
|---|---|---|---|---|---|---|---|---|---|---|---|
| baseline_dense_only (docs thresholds) | all | 0.9977 | 0.6751 | 0.8053 | 0.5825 | 0.9555 | 0.0147 | 1 | 0.3119 | 0.2807 | 1.0 |
| docs_starting_config (dense + time) | all | 0.9889 | 0.6942 | 0.8158 | 0.6395 | 0.957 | 0.0435 | 2 | 0.3028 | 0.3977 | 0.9189 |
| tuned_on_half_A | tune_half_A | 0.9744 | 0.9949 | 0.9845 | 0.9448 | 0.995 | 0.0317 | 2 | 0.0154 | 0.9877 | 0.8696 |
| tuned_on_half_A | heldout_half_B | 0.9844 | 1.0 | 0.9922 | 0.9625 | 0.9976 | 0.012 | 1 | 0.0124 | 1.0 | 0.9375 |
| tuned_on_half_A | all | 0.9428 | 0.9931 | 0.9673 | 0.8942 | 0.9909 | 0.0719 | 8 | 0.0298 | 0.9825 | 0.7636 |

Tuned config (chosen on half A only): `{'time_w': 0.1, 'thresholds': {'high': 0.72, 'low': 0.62}, 'borderline': 'new_story'}`
