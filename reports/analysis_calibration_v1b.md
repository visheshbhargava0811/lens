# Story analysis eval: calibration_v1b

Generated 2026-09-23T14:35 UTC. Raw numbers: `reports/analysis_calibration_v1b.json`.
Inputs are headlines and feed summaries only (snippet_only).

| Metric | Value |
|---|---|
| Stories analysed / summary versions | 225 / 243 |
| Outcomes | failed 201, published 35, rejected 1, review 6 |
| Summary attempts (1 = passed first time) | 1: 14, 2: 6, 3: 223 |
| Versions with judge-pruned sentences | 20 |
| G-GEN-03 judge pass rate (per check) | 0.206 |
| Guard pass rates | G-GEN-01 1.0, G-GEN-02 0.846, G-GEN-03 0.206, G-OUT-07 0.833 |
| Stored claims / quote-match rate (re-checked) | 532 / 1.0 |
| Versions with framing differences | 72 |

## Judge calibration (`data/evals/judge_calibration/gold_v1.jsonl`)

Judge `groq/qwen/qwen3.8-27b` (primary only). n = 122 (0 unscored: judge unavailable), Cohen's kappa = **0.473** (target 0.6), raw agreement 0.803, human-supported share 0.836.

Confusion: both supported 81, both unsupported 17, **judge too strict 21** (rejects what the person accepts), **judge too lenient 3** (accepts what the person rejects).

| Languages | n | kappa | agreement |
|---|---|---|---|
| en | 52 | 0.305 | 0.75 |
| en+hi | 40 | 0.357 | 0.775 |
| en+hi+mr | 8 | 0.0 | 0.75 |
| en+mr | 2 | 1.0 | 1.0 |
| hi | 20 | 1.0 | 1.0 |
