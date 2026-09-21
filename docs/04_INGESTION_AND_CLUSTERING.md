# 04 Ingestion and clustering (Graph 1)

Clustering quality decides whether the product works. A chat interface over badly clustered data produces confident nonsense. Get this right and measured before building the Ask agent.

## Node list

| # | Node | Type | Input | Output | Idempotency key |
|---|---|---|---|---|---|
| 1 | Fetcher | Tool node, no LLM | source feed config | raw article rows | `(source_id, canonical_url)` |
| 2 | Triage | Classifiers, small model | raw article | language, is_news, cleaned text, syndication flags | `article_id` |
| 3 | Entity and event | Small LLM, structured | cleaned article | `ArticleEntities` | `article_id, schema_version` |
| 4 | Chunk and embed | Deterministic + embedding model | cleaned article | chunks, Qdrant points | `article_id` |
| 5 | Clusterer | Embeddings + rules, no LLM | article vectors, story index | story assignment or candidate | `article_id` |
| 6 | Cluster verifier | LLM, structured, borderline only | article + candidate story | `ClusterDecision` | `article_id, story_id` |
| 7 | Claim extraction | LLM, structured | article | `ClaimList` (quote-verified) | `article_id, schema_version` |
| 8 | Framing and stance | LLM, structured | articles in story | `Framing` per article, `StoryFraming` | `story_id, article_id` |
| 9 | Fact-check matcher | Retrieval + LLM verify | checkable claims | matches | `claim_id` |
| 10 | Story summarizer | LLM, structured | balanced evidence set | `StorySummary` | `story_id, version` |
| 11 | Stats and blindspots | Deterministic | story data | `story_stats` | `story_id` |

Each node: typed input and output, a timeout, retries with backoff, failures to `dead_letters`, and a named LangSmith run.

## 1. Fetcher

- Poll each source on its own interval (start at 10 to 15 minutes). Use ETag and If-Modified-Since.
- Read feeds with `feedparser`. For sources with no feed, prefer sitemaps or news APIs. Scrapy or Playwright only as a last resort and only where `robots_ok` and terms permit.
- Respect `robots.txt` at fetch time. Store `robots_ok` per source.
- Enforce `license_mode`:
  - `full_text`: extract with `trafilatura`, store `full_text`.
  - `snippet_only`: store title and feed snippet only. `analysis_depth` is `snippet` (or `headline_only` if no snippet).
  - `link_only`: store title, URL, timestamp only.
- Dedup by `canonical_url` and `content_hash`.
- Never fetch or store images unless `image_policy = hotlink`, and then only the URL.

**Consequence to design for:** for `snippet_only` and `link_only` sources, downstream nodes only see limited text. Claims and framing for those articles are weaker. Mark `analysis_depth` and show it in the UI ("Based on headline and summary"). Do not pretend depth we do not have.

## 2. Triage

- Language ID with `lingua` or fastText. Detect romanized Hindi (`hi-Latn`). Store confidence.
- `is_news` filter: rules (URL patterns, section) first, small classifier second. Drop opinion-only, listicles, horoscopes, sponsored content, and clear spam. Keep `opinion` as a flag if useful, but exclude from the coverage bar.
- Boilerplate removal for full-text sources.
- **Syndication detection:**
  - Wire markers in byline or dateline (PTI, ANI, IANS, Reuters, AP, and others from `sources.is_wire`).
  - SimHash or MinHash near-duplicate against articles from the last 72 h.
  - If detected, set `is_syndicated`, `syndicated_from`, and `original_article_id`. Syndicated copies count as **one source** in stats. The original wire item is kept as the representative.

## 3. Entity and event

Small model, structured output (`ArticleEntities`): people, organizations, parties, places, event type, event date, and named institutions. Entities must appear in the text. Keep original script. Used as clustering features and for guards.

## 4. Chunk and embed

### Semantic chunking (Indic-aware)

- Sentence split on `.`, `?`, `!`, and the Devanagari danda `।` (and double danda `॥`).
- Embed sentences, split where adjacent-sentence distance exceeds a percentile threshold, with min and max sizes.
- Keep `char_start` and `char_end` for every chunk. Quote verification and citation highlighting depend on them.
- For short articles, benchmark against paragraph-aware recursive chunking. Keep semantic chunking only if retrieval metrics improve (see `docs/08`).

```python
import re
import numpy as np

SENT_SPLIT = re.compile(r'(?<=[.!?।॥])\s+')

def semantic_chunks(text: str, embed, pct: int = 90, min_sents: int = 2, max_chars: int = 1200):
    spans, pos = [], 0
    for s in SENT_SPLIT.split(text):
        start = text.index(s, pos)
        pos = start + len(s)
        spans.append((start, pos))
    sents = [text[a:b] for a, b in spans]
    if len(sents) < 2:
        return [{"text": text, "start": 0, "end": len(text)}]
    E = np.asarray(embed(sents))                    # L2-normalized
    dist = 1 - (E[:-1] * E[1:]).sum(1)
    cut = np.percentile(dist, pct)
    chunks, s0 = [], 0
    for i, d in enumerate(dist):
        size = spans[i][1] - spans[s0][0]
        if (d > cut and i + 1 - s0 >= min_sents) or size > max_chars:
            chunks.append((s0, i))
            s0 = i + 1
    chunks.append((s0, len(sents) - 1))
    return [{"text": text[spans[a][0]:spans[b][1]],
             "start": spans[a][0], "end": spans[b][1]} for a, b in chunks]
```

Note the sentence-embedding pass is separate from chunk embedding. For very short articles (snippets), skip chunking and use one chunk.

### Embedding

BGE-M3 via FlagEmbedding produces dense, sparse (lexical weights), and multivector outputs in one forward pass. Compute all three, write to Qdrant `chunks`. Prepend `"{outlet} | {date} | {headline}\n"` to the embedded text only, not the stored text.

Also compute an **article vector**: L2-normalized mean of the article's chunk dense vectors (or title + lede embedding for snippets). Used for clustering.

## 5. Clusterer

Goal: group articles about the **same event**, across languages, without translating.

Same topic is not same event. "Iran-US tensions" is a topic. "US strike on X on 21 Sept" is an event. Cluster by event.

### Incremental assignment (per new article)

1. Candidate stories: search Qdrant `stories` by article vector, filtered to `last_updated_at` within `window_hours` (start 72).
2. Compute a combined score against each of the top 5 candidates:

   `S = w_cos * cosine + w_ent * entity_jaccard + w_time * time_proximity + w_type * event_type_match`

3. Decide:
   - `S >= T_high`: assign automatically.
   - `T_low <= S < T_high`: send to the Cluster verifier.
   - `S < T_low`: create a new story.

Starting values in `config/clustering.yaml` (tune on the eval set, these are guesses):

```yaml
window_hours: 72
weights: { cos: 0.6, entity_jaccard: 0.2, time: 0.1, event_type: 0.1 }
thresholds: { high: 0.82, low: 0.68 }
story_centroid_update: running_mean
lifecycle: { stable_after_hours: 24, archive_after_days: 7 }
min_sources_for_bar: 4
```

### Nightly batch pass

HDBSCAN over the last 7 days of article vectors, plus the same feature scores, to propose merges and splits. **Merges and splits require verifier approval.** Never auto-merge two large stories.

### Cluster verifier (LLM)

Input: the new article (title, lede, entities, date) and the candidate story (headline, entities, 3 representative articles). Output `ClusterDecision`:
- `rationale` first, then `same_event: yes | no | uncertain`.
- `uncertain` creates a new story and logs to the review queue if the score was near `T_high`.

Only borderline cases go to the LLM. Track the share of articles hitting the verifier. It should be small.

### Story lifecycle and updates

- `developing` while new articles arrive within 24 h, then `stable`, then `archived`.
- After each assignment, update the centroid, counts, and `last_updated_at`.
- Trigger downstream re-analysis when the story gains a material number of new sources (start: 3 new sources or 6 hours) rather than on every article.

## 6 and 7. Claims

`ClaimList` from an analysis-tier model. For each claim: one atomic checkable statement, a **verbatim** `source_quote`, offsets, attribution, and `checkable`.

**Deterministic quote check:** the quote must appear in the article text (normalize whitespace and Unicode NFC only). Failing claims are dropped and counted. If more than 20% of an article's claims fail, flag the article for prompt review.

## 8. Framing and stance

Two passes per story:

1. **Per-article, source-masked:** the prompt contains the article text and story headline, **not the outlet name**. Output `Framing` with `rationale` first, then `stance_target`, `stance`, `stance_confidence`. This is what feeds the coverage bar.
2. **Contrastive, per story:** given all masked article framings, output `StoryFraming`: how framings differ, what each group emphasizes, what appears in some coverage and not others. Then re-attach outlet names in code, not in the prompt.

Rules:
- Low confidence becomes `unclassified` in stats.
- `not_applicable` when there is no government or opposition angle (sports, weather, most business news).
- The stance rubric lives in `agents/skills/stance_rubric.md` and is versioned. Definitions are in `docs/13_INDIA_SOURCES.md`.
- Run the masked-source audit and symmetry audit (guards `G-BIAS-02`, `G-BIAS-03`) in evals.

## 9. Fact-check matcher

- Ingest fact-check items (Google Fact Check Tools API / ClaimReview markup, plus direct feeds). Embed `claim_reviewed` into Qdrant `fact_checks`.
- For each checkable claim, retrieve top 5 fact-checks (dense, same language plus cross-lingual).
- LLM verifier decides `same_claim | related | different` with rationale first. Store only `same_claim` and `related`.
- Never present a match as our verdict. Show the fact-checker's name, rating, and link.

## 10. Story summarizer

Runs on a **source-balanced evidence set** (see `docs/05`). Output `StorySummary`: cited sentences for summary, agreements, disagreements. Pipeline: schema check, deterministic quote and citation check, judge verification, output guards (`docs/07`). Store versioned. Stories in sensitive categories go to the review queue before publishing (`G-OUT-07`).

## 11. Stats and blindspots

Pure code. Given articles for a story after syndication dedup:
- `stance_counts` by distinct source
- `factuality_counts` from third-party ratings (unrated counted as unrated)
- `ownership_counts` by parent group where known
- `language_counts`
- `coverage_confidence`: based on source count, unclassified share, and average stance confidence
- Blindspot detection per `docs/01_PRODUCT.md`

Unit test the math thoroughly. This is the number users see.

## Scheduling

- Cron or Arq scheduler for fetch, per-source interval
- Article-level nodes run as queued jobs as articles arrive
- Story-level nodes (framing, summary, stats) run on the update trigger above
- Nightly: batch re-cluster, archive stories, purge expired logs, drop expired ColBERT vectors
- Move to Airflow only if orchestration complexity demands it

## Clustering evaluation (build before tuning)

Dataset: `data/evals/clustering/*.jsonl`, **at least 100 human-labeled stories**, with:
- at least 30 cross-lingual stories (same event in Hindi and English)
- at least 20 hard negatives (same topic, different event)
- at least 10 developing stories that grow over several hours

Metrics: B-cubed precision/recall/F1, ARI, V-measure, cross-lingual pair accuracy, merge error rate, verifier call rate. Record baseline in `reports/clustering_baseline.md`. Fine-tune embeddings only if the baseline shows a measurable gap (contrastive pairs from verified clusters).

Claude Code should build the labeling **export format and script**. Humans do the labeling.
