# Reviewing the retrieval eval queries

`to_review_v1.csv` lists 172 search queries drafted by Claude from real stories in the corpus. Each row shows the headline(s) of the story (or stories) that should be found for that query. Your review decides whether the set can be trusted for the Phase 5 ablation (docs/05, docs/08).

Open it in **Google Sheets** (Hindi and Marathi text).

## For each row

- `correct`: **yes** if the listed story is what a reader searching that query wants; **no** if not.
- `fix_or_note`: when **no**, say what is wrong: wrong story, a story is missing (another event with the same topic also belongs), or the query is unclear.

## What to check

- **Does the query describe the listed story's event?** Paraphrases and translations are intended. `cross_lingual` queries deliberately use a different language from most of the coverage.
- **`no_answer` rows** list no story on purpose: nothing in the last few days of news should match (for example an old sports final). Mark **no** if you know the corpus does cover it.
- **`loaded` rows** are deliberately biased phrasings ("why is X rigging..."). The listed neutral story is still the right answer. Judge the story, not the wording.

## How many

At least **40 rows** (the file is shuffled, so the first 40 are a fair sample). All 172 is better. Expect about 20 seconds per row.

Save as CSV (UTF-8) in this folder and tell Claude. Agreement with the draft is recorded, and your fixes become `queries_v1.jsonl`.
