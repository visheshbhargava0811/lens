# Language ID baseline (Phase 1A)

Detector: `lens.ingest.triage.detect_language`. Unicode script decides first. lingua 2.2.0 separates languages that share a script, after a lexical vote for Hindi vs Marathi and a function-word check for romanized Hindi (`hi-Latn`).

## Datasets

| Split | File | Size | Labels |
|---|---|---|---|
| dev | `data/evals/langid/sample_v1.jsonl` | 140 | 110 random ingested headlines (40 from English outlets, 40 Hindi, 30 Marathi), each read and labeled. 20 romanized-Hindi queries and 10 English sentences with Hindi loanwords, hand-written |
| held-out | `data/evals/langid/heldout_v1.jsonl` | 100 | 80 new random headlines (20 en, 30 hi, 30 mr) plus 10 romanized-Hindi and 10 loanword sentences written after tuning. Never used for tuning |

**Labeler:** Claude, on 2026-09-21. The labels still need a person to check them, especially the short Marathi headlines marked "hard".

## Results

| Run | Split | Accuracy | en | hi | mr | hi-Latn |
|---|---|---|---|---|---|---|
| Baseline: lingua for hi/mr, first Hinglish word list | dev | 0.907 | 0.96 | 0.80 | 0.967 | 0.90 |
| After: hi/mr lexical vote, word list without English collisions | dev | 1.000 | 1.00 | 1.00 | 1.00 | 1.00 |
| After (the number to trust) | held-out | **0.970** | 1.00 | 1.00 | 0.967 | 0.80 |

Raw outputs are in `reports/langid_*.json`.

## Errors and known weaknesses

- **Baseline:** lingua called 8 of 40 short Hindi headlines Marathi. The first Hinglish list contained "the" and "me", which are also English words, so it flagged English sentences as `hi-Latn`.
- **Held-out:**
  - "ऊर्जा प्रबोधन मोहीम" (Marathi, 3 words, no function words) was called Hindi.
  - Two romanized-Hindi questions with only one Hindi function word were called English.
- **Romanized Hindi is the weak spot.** A word-list rule tops out quickly. It matters most for Ask queries (Phase 6), where a small model in the `query_understanding` tier should decide instead. Revisit it there with a larger held-out set.
- **Languages not covered:** Tamil, Bengali and the other script-unique languages aren't in these sets. Script detection is near-certain for them, but add them when the regional language changes.

## Production check (2026-09-21)

After reprocessing all 4,365 stored articles, 13 (0.3%) got a language different from their outlet's. These are mostly bilingual headlines ("Malkapur Auto Garage Battery Theft, One Thief Caught: गॅरेज…") and very short Marathi headlines. For Hindi vs Marathi, the language the feed declares is used only to break a tie when the text gives no evidence either way. It never overrides the text.
