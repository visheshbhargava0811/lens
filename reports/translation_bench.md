# Translation benchmark (40 sentences from verified answers and summaries)

Scores without human references: G-OUT-06 (numbers, attribution, names) and an independent judge
(Qwen, binary faithful). `G-OUT-06 first` is the check before tuning on this set, `now` after.

| System | Lang | G-OUT-06 first | G-OUT-06 now | Judge faithful | Both now | s/sentence |
|---|---|---|---|---|---|---|
| groq/openai/gpt-oss-120b | hi | 0.700 | 0.975 | 0.925 | 0.900 | 0.21 |
| groq/openai/gpt-oss-120b | mr | 0.700 | 0.975 | 1.000 | 0.975 | 0.18 |
| groq/openai/gpt-oss-20b | hi | 0.700 | 0.975 | 0.925 | 0.900 | 0.11 |
| groq/openai/gpt-oss-20b | mr | 0.600 | 0.950 | 0.975 | 0.925 | 0.07 |
| gemini/gemini-3.6-flash | hi | 0.675 | 0.950 | 1.000 | 0.950 | 0.61 |
| gemini/gemini-3.6-flash | mr | 0.700 | 0.975 | 1.000 | 0.975 | 1.06 |

Not benchmarked (owner action needed):
- sarvam-translate: Sarvam returns 402 'No credits available' (checked 2026-09-27)
- bhashini: BHASHINI_KEYS is empty
- indictrans2-en-indic-dist-200M: gated on Hugging Face: accept the licence and log in (huggingface-cli login)
