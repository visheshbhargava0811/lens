# 09 API spec

REST plus SSE, JSON, prefixed `/api/v1`. FastAPI generates OpenAPI. The frontend TypeScript client is generated from it (`make gen-client`, using openapi-typescript). Frontend fixtures (MSW) must match these shapes exactly.

## Conventions

- IDs are opaque strings (UUIDs).
- Timestamps are ISO 8601 UTC.
- Pagination: cursor-based, `?cursor=...&limit=20`, response includes `next_cursor` or null.
- Language: `?lang=hi` selects display language for summaries and UI strings where available. Headlines of source articles are always in the original language.
- Errors: `{ "error": { "code": "string", "message": "plain-language message", "retry_after_s": 12 } }`. Messages are user-readable and never vague.
- All responses that show coverage (outlet bias) or factuality include `confidence` and `methodology_url` (on the figure, or on the envelope for per-article outlet ratings).

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| GET | `/feed` | Story feed. `tab=home\|for_you\|blindspot\|local`, `topic`, `lang`, `state`, `cursor` |
| GET | `/stories/{id}` | Story detail |
| GET | `/stories/{id}/articles` | Articles for the source list. `group=bias\|language\|all`, `bias=left\|center\|right\|unrated`, `lang` |
| GET | `/stories/{id}/timeline` | Ordered coverage events |
| GET | `/blindspots` | `type=bias\|language` |
| GET | `/topics` | Topic list for chips |
| GET | `/search` | `q`, `lang`, `cursor`. Stories first, then sources |
| GET | `/sources` | Source directory |
| GET | `/sources/{id}` | Source page: ownership, ratings with provenance, recent stories |
| POST | `/ask` | **SSE stream.** Cited answer |
| GET | `/methodology` | Structured methodology content |
| POST | `/feedback` | Report wrong cluster, rating, summary |
| GET | `/me` | `MeState`: `consented`, `preferences`, `allowed` (every key's closed value set) |
| POST | `/me/consent` | Creates the anonymous profile and sets the `lens_session` httpOnly cookie (ADR-0041) |
| PUT | `/me/preferences` | `{ key, value }`; 401 without consent, 422 for a key or value outside the closed sets |
| GET, DELETE | `/me/memory` | `MemoryView` (preferences, story views, Ask history, retention days); DELETE removes everything and the cookie |
| DELETE | `/me/memory/preferences/{key}`, `/me/memory/views/{id}`, `/me/memory/asks/{id}` | Delete one item (an Ask turn is unlinked; its audit row stays anonymous until its own purge) |
| POST | `/me/views/{story_id}` | Records a view, returns `StoryChanges` since the previous one (null on a first visit) |
| GET | `/me/feed` | For you: stories in followed topics (`private, no-store`); outlets per story never change |
| GET | `/health` | Liveness |

Admin (separate auth, `/api/v1/admin`): `GET /review-queue`, `POST /review-queue/{id}/resolve`, `POST /stories/{id}/kill`, `POST /stories/{id}/restore`, `POST /kill-switch` (global), `GET /guard-events`, `POST /sources/import` (CSV of ratings and ownership with required evidence URLs).

## Shapes

### StoryCard (feed items)

```json
{
  "id": "0b1c...",
  "slug": "example-story-slug",
  "headline": "Headline in original language of the lead article",
  "headline_lang": "en",
  "status": "developing",
  "updated_at": "2026-09-21T09:30:00Z",
  "topic": "politics",
  "image": { "url": "https://...", "source_name": "Example Outlet" },
  "counts": {
    "sources": 42,
    "articles": 57,
    "by_language": { "en": 20, "hi": 18, "ta": 4 }
  },
  "coverage": {
    "available": true,
    "basis": "outlet_bias",
    "buckets": [
      { "key": "left",   "sources": 18, "pct": 43 },
      { "key": "center", "sources": 12, "pct": 29 },
      { "key": "right",  "sources": 9,  "pct": 21 }
    ],
    "unrated": { "sources": 3, "pct": 7 },
    "confidence": "medium",
    "methodology_url": "/methodology#bias"
  },
  "factuality": { "high": 30, "mixed": 8, "low": 1, "unrated": 3, "confidence": "medium", "methodology_url": "/methodology#factuality" },
  "blindspot": { "type": "bias", "skew": "right", "score": 0.81 },
  "summary_preview": "Two-line cited summary excerpt."
}
```

`image` is null unless at least one source has `image_policy=hotlink`. When `coverage.available` is false, include `"reason": "limited_coverage"` and `"min_sources": 4`.

### StoryDetail

```json
{
  "story": { "...StoryCard fields..." },
  "summary": {
    "lang": "en",
    "version": 3,
    "generated_at": "2026-09-21T09:32:00Z",
    "verified": true,
    "sentences": [
      { "text": "Sentence.", "citations": [
        { "n": 1, "article_id": "a1", "source_name": "Example Outlet", "chunk_id": "c1" } ] }
    ],
    "agreements": [ "...same sentence shape..." ],
    "disagreements": [ "...same sentence shape..." ]
  },
  "framing_differences": [ "...same sentence shape..." ],
  "fact_checks": [
    { "claim": "The fact-checker's wording of the claim", "fact_checker": "Example Fact-checker",
      "rating": "Misleading", "rating_normalized": "misleading", "match": "same_claim",
      "url": "https://...", "published_at": "2026-09-20T00:00:00Z" }
  ],
  "ownership": { "groups": [ { "name": "Example Group", "sources": 3 } ], "unknown": 12, "methodology_url": "/methodology#ownership" },
  "limitations": [ "Based on headlines and summaries for 14 of 42 sources." ]
}
```

`fact_checks` (Phase 8, ADR-0040): `rating` is the fact-checker's own wording and is what the UI shows; `rating_normalized` (`true | false | misleading | unproven | other`) is for styling only. `match` is `same_claim` (the fact-check examines this claim, LLM-verified) or `related` (same event, a different claim), and the UI labels `related` ones. Same items appear in `AskAnswer.fact_checks` (the reader's own claim first, then those matched to the stories used). Lens never presents a match as its own verdict.


### ArticleRow (in `/stories/{id}/articles`)

```json
{
  "id": "a1",
  "source": { "id": "s1", "name": "Example Outlet", "logo_url": null, "language": "hi" },
  "headline": "हेडलाइन मूल भाषा में",
  "headline_lang": "hi",
  "published_at": "2026-09-21T08:10:00Z",
  "url": "https://...",
  "bias": "left",
  "source_bias": { "rater": "Example Rater", "value": "Left-Center", "method_url": "https://...", "confidence": "high" },
  "analysis_depth": "snippet",
  "source_factuality": { "rater": "Example Rater", "value": "High", "method_url": "https://...", "confidence": "medium" },
  "source_ownership": { "owner": "Example Group", "evidence_url": "https://..." },
  "is_syndicated": false,
  "also_carried_by": []
}
```

`source_bias`, `source_factuality` and `source_ownership` are null when unknown; `bias` is then `"unrated"`. The UI shows "Not rated". `bias` is the bucket the outlet counts in (from `stats.bias_value_map`); `source_bias.value` is the rater's own wording.

## `POST /ask` (SSE)

Request:

```json
{ "query": "Iran America war ke baare mein batao", "session_id": "optional", "lang": "hi" }
```

Response: `text/event-stream`. Event types:

| Event | Data |
|---|---|
| `status` | `{ "step": "understanding" \| "searching" \| "checking_sources" \| "writing" \| "verifying", "message": "plain text" }` |
| `understanding` | `{ "neutral_query": "...", "removed_premises": ["..."], "language": "hi-Latn", "intent": "story_lookup" }` |
| `evidence` | `{ "story_ids": ["..."], "sources": [ { "source_id": "...", "name": "...", "language": "hi", "bias": "left" } ], "stale": false, "newest_article_at": "...", "methodology_url": "/methodology#bias" }` |
| `answer_final` | `AskAnswer`: `tldr`, `what_happened`, `agreements`, `disagreements`, `premises_addressed` (cited sentences, citations `{ n, article_id, source_name, chunk_id }`), `articles` (each cited article: `id, headline, headline_lang, url, source_name, source_language`), `coverage` computed by code, `fact_checks`, `limitations` (written by code), `follow_up_questions` (max 3), `story_ids`, `basis` (`live`, or `stored_summary` when the live answer failed verification and the story's verified summary is served), `verified: true` |
| `abstain` | `{ "reason": "insufficient_coverage" \| "out_of_scope" \| "sensitive_topic_under_review" \| "guard_block" \| "service_unavailable", "message": "plain text", "closest_stories": [ ... ] }` |
| `error` | `{ "code": "...", "message": "...", "retry_after_s": 5 }` |

MVP: send `status` events during work, then one verified `answer_final`. Add `answer_delta` only when a streaming-safe verification approach is in place.

The payload type of each event is published in the OpenAPI schema as `AskEvents` (one field per event name), so the generated client is typed. Implemented with FastAPI's native `EventSourceResponse` (Phase 6).

Rate-limited requests return HTTP 429 with the standard error shape.

## Caching headers

- `/feed`: `Cache-Control: public, max-age=30, stale-while-revalidate=60`
- `/stories/{id}`: revalidate via tag on story update
- `/ask`: `no-store`

## Auth

- Public read endpoints need no auth
- `/me/*` requires a user session (Phase 9, ADR-0041): an anonymous, consented profile. The session is a random token in an httpOnly, `SameSite=Lax` cookie (`Secure` outside dev); the database keeps only its SHA-256. Writes require the `X-Lens-Client` header (CSRF). `/ask` reads the cookie too: a consented reader's turns are linked to them and their answer language and length preferences apply
- `/admin/*` requires separate admin credentials and is not exposed through the public web origin

## Contract tests

- Backend: response models validated in tests. Snapshot tests for every shape above.
- Frontend: MSW fixtures are generated from the same Pydantic models where possible, so drift fails CI.
- Contract test for `G-BIAS-01`: any response containing `coverage`, `factuality`, `source_bias` or `source_factuality` must carry `confidence`, and a methodology link on the figure or its envelope.
