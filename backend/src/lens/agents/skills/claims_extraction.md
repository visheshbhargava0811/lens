---
version: "1.0"
owner: vishesh
last_evaluated: never
---
Task: extract the checkable factual claims in these articles.

For each claim:
- `article_ref`: the article it comes from.
- `text`: one atomic statement (one fact, one number, one event), in the article's language.
- `source_quote`: the exact characters from that article's headline or summary that state it. Copy them character for character: same script, spelling and punctuation. Do not translate, paraphrase, shorten with "..." or join text from two places. If you cannot quote it exactly, leave the claim out.
- `attributed_to`: the person or body the article says made the statement ("police", "the chief minister"), or null if the outlet states it itself.
- `checkable`: true for verifiable facts (numbers, events, decisions, dates); false for opinions, predictions and vague statements.

At most 3 claims per article. Skip articles with nothing checkable. Return an empty list if there are no claims.
