# Story analysis eval: calibration_v3a_refs

Generated 2026-09-23T16:03 UTC. Raw numbers: `reports/analysis_calibration_v3a_refs.json`.
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

Judge `groq/qwen/qwen3.8-27b` (primary only). n = 3 (51 unscored: judge unavailable), Cohen's kappa = **None** (target 0.6), raw agreement 1.0, human-supported share 1.0.

Confusion: both supported 3, both unsupported 0, **judge too strict 0** (rejects what the person accepts), **judge too lenient 0** (accepts what the person rejects).

| Languages | n | kappa | agreement |
|---|---|---|---|
| en | 1 | None | 1.0 |
| hi | 2 | None | 1.0 |
