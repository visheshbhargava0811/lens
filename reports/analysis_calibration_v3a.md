# Story analysis eval: calibration_v3a

Generated 2026-09-23T15:55 UTC. Raw numbers: `reports/analysis_calibration_v3a.json`.
Inputs are headlines and feed summaries only (snippet_only).

| Metric | Value |
|---|---|
| Stories analysed / summary versions | 228 / 290 |
| Outcomes | failed 201, published 77, rejected 1, review 11 |
| Summary attempts (1 = passed first time) | 1: 49, 2: 13, 3: 228 |
| Versions with judge-pruned sentences | 34 |
| G-GEN-03 judge pass rate (per check) | 0.38 |
| Guard pass rates | G-GEN-01 1.0, G-GEN-02 0.855, G-GEN-03 0.38, G-GEN-08 0.755, G-OUT-07 0.865 |
| Stored claims / quote-match rate (re-checked) | 725 / 1.0 |
| Versions with framing differences | 119 |

## Judge calibration (`data/evals/judge_calibration/gold_v3a.jsonl`)

Judge `groq/qwen/qwen3.8-27b` (primary only). n = 39 (15 unscored: judge unavailable), Cohen's kappa = **0.389** (target 0.6), raw agreement 0.821, human-supported share 0.923.

Confusion: both supported 29, both unsupported 3, **judge too strict 7** (rejects what the person accepts), **judge too lenient 0** (accepts what the person rejects).

| Languages | n | kappa | agreement |
|---|---|---|---|
| en | 17 | 0.0 | 0.882 |
| en+hi | 15 | 0.471 | 0.8 |
| hi | 7 | 0.364 | 0.714 |
