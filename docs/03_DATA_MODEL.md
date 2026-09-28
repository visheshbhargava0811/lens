# 03 Data model

Postgres holds relational truth. Qdrant holds vectors. Every Qdrant point carries `article_id`, `story_id`, and `source_id` in its payload so retrieval can filter and expand.

Implement this as SQLAlchemy models plus Alembic migrations. The DDL below is the reference. Adjust types to fit SQLAlchemy idioms, keep names.

## Enums

```sql
CREATE TYPE license_mode   AS ENUM ('full_text', 'snippet_only', 'link_only');
CREATE TYPE image_policy   AS ENUM ('hotlink', 'none');
CREATE TYPE stance         AS ENUM ('critical', 'balanced', 'supportive', 'not_applicable', 'unclassified');
CREATE TYPE stance_target  AS ENUM ('central_govt', 'state_govt', 'opposition', 'none');
CREATE TYPE confidence     AS ENUM ('low', 'medium', 'high');
CREATE TYPE story_status   AS ENUM ('developing', 'stable', 'archived');
CREATE TYPE analysis_depth AS ENUM ('headline_only', 'snippet', 'full_text');
```

## Sources and metadata

```sql
CREATE TABLE sources (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  slug          text UNIQUE NOT NULL,
  name          text NOT NULL,
  homepage_url  text NOT NULL,
  language_codes text[] NOT NULL,            -- ISO 639-1/3, e.g. {'en'}, {'hi'}
  country       text NOT NULL DEFAULT 'IN',
  region        text,                        -- state or national
  feed_urls     jsonb NOT NULL DEFAULT '[]', -- [{url, kind: rss|api|sitemap, topic?}]
  license_mode  license_mode NOT NULL DEFAULT 'snippet_only',
  image_policy  image_policy NOT NULL DEFAULT 'none',
  robots_ok     boolean NOT NULL DEFAULT true,
  is_wire       boolean NOT NULL DEFAULT false,   -- PTI, ANI, Reuters, etc.
  is_fact_checker boolean NOT NULL DEFAULT false,
  active        boolean NOT NULL DEFAULT true,
  created_at    timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE source_ownership (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  source_id     uuid NOT NULL REFERENCES sources(id),
  owner_name    text NOT NULL,
  owner_type    text,               -- conglomerate | trust | individual | government | other
  parent_group  text,
  evidence_url  text NOT NULL,      -- required
  retrieved_at  timestamptz NOT NULL,
  verified_by   text,
  confidence    confidence NOT NULL
);

CREATE TABLE source_ratings (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  source_id     uuid NOT NULL REFERENCES sources(id),
  dimension     text NOT NULL,      -- factuality | stance_history | other
  rater         text NOT NULL,      -- name of third-party rater or 'internal'
  value         text NOT NULL,
  numeric_value real,
  method_url    text NOT NULL,      -- required
  evidence_url  text,
  retrieved_at  timestamptz NOT NULL,
  confidence    confidence NOT NULL
);
CREATE INDEX ON source_ratings (source_id, dimension);
```

## Articles and chunks

```sql
CREATE TABLE articles (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  source_id       uuid NOT NULL REFERENCES sources(id),
  url             text NOT NULL,
  canonical_url   text UNIQUE NOT NULL,
  title           text NOT NULL,
  snippet         text,
  full_text       text,                       -- NULL unless license_mode = full_text
  analysis_depth  analysis_depth NOT NULL,
  language        text NOT NULL,              -- detected, ISO code, 'hi-Latn' for romanized Hindi
  language_conf   real,
  published_at    timestamptz NOT NULL,
  fetched_at      timestamptz NOT NULL DEFAULT now(),
  byline          text,
  content_hash    text NOT NULL,
  simhash         bigint,
  is_news         boolean NOT NULL DEFAULT true,
  is_syndicated   boolean NOT NULL DEFAULT false,
  syndicated_from text,                       -- 'PTI', 'ANI', 'Reuters', ...
  original_article_id uuid REFERENCES articles(id),
  image_url       text,                       -- only if source.image_policy = hotlink
  entities        jsonb,                      -- ArticleEntities
  event_type      text,
  schema_version  text NOT NULL,
  UNIQUE (source_id, url)
);
CREATE INDEX ON articles (published_at DESC);
CREATE INDEX ON articles (source_id, published_at DESC);
CREATE INDEX ON articles (simhash);

CREATE TABLE chunks (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  article_id      uuid NOT NULL REFERENCES articles(id) ON DELETE CASCADE,
  idx             int  NOT NULL,
  text            text NOT NULL,              -- raw text, original script
  char_start      int  NOT NULL,              -- offsets into the article text used
  char_end        int  NOT NULL,
  token_count     int  NOT NULL,
  qdrant_point_id uuid NOT NULL,
  UNIQUE (article_id, idx)
);
```

`char_start` and `char_end` index into whichever text was analyzed (`full_text` if present, else `title + "\n" + snippet`). Store which one in the chunk metadata if that is ever ambiguous.

## Stories

```sql
CREATE TABLE stories (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  slug            text UNIQUE NOT NULL,
  headline        text NOT NULL,
  headline_lang   text NOT NULL,
  status          story_status NOT NULL DEFAULT 'developing',
  topic           text,
  region          text,                        -- state code if local
  first_seen_at   timestamptz NOT NULL,
  last_updated_at timestamptz NOT NULL,
  article_count   int NOT NULL DEFAULT 0,
  source_count    int NOT NULL DEFAULT 0,      -- distinct, after syndication dedup
  languages       text[] NOT NULL DEFAULT '{}',
  kill_switch     boolean NOT NULL DEFAULT false,
  review_status   text NOT NULL DEFAULT 'auto' -- auto | pending | approved | held
);
CREATE INDEX ON stories (last_updated_at DESC);
CREATE INDEX ON stories (topic, last_updated_at DESC);

CREATE TABLE story_articles (
  story_id    uuid NOT NULL REFERENCES stories(id) ON DELETE CASCADE,
  article_id  uuid NOT NULL REFERENCES articles(id) ON DELETE CASCADE,
  similarity  real,
  method      text NOT NULL,                   -- auto | verifier | batch | manual
  assigned_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (story_id, article_id)
);

CREATE TABLE story_stats (
  story_id          uuid PRIMARY KEY REFERENCES stories(id) ON DELETE CASCADE,
  computed_at       timestamptz NOT NULL,
  stance_counts     jsonb NOT NULL,      -- {critical: n, balanced: n, supportive: n, unclassified: n} distinct sources
  factuality_counts jsonb NOT NULL,      -- {high, mixed, low, unrated}
  ownership_counts  jsonb NOT NULL,
  language_counts   jsonb NOT NULL,
  coverage_confidence confidence NOT NULL,
  blindspot_type    text,                -- stance | language | NULL
  blindspot_skew    text,                -- which group dominates
  blindspot_score   real
);
```

## Analysis outputs

```sql
CREATE TABLE claims (
  id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  article_id     uuid NOT NULL REFERENCES articles(id) ON DELETE CASCADE,
  text           text NOT NULL,
  source_quote   text NOT NULL,          -- verbatim, verified against article text
  char_start     int NOT NULL,
  char_end       int NOT NULL,
  attributed_to  text,
  checkable      boolean NOT NULL,
  schema_version text NOT NULL
);

CREATE TABLE framings (
  id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  article_id        uuid NOT NULL REFERENCES articles(id) ON DELETE CASCADE,
  story_id          uuid NOT NULL REFERENCES stories(id) ON DELETE CASCADE,
  rationale         text NOT NULL,
  headline_framing  text NOT NULL,
  tone              text NOT NULL,
  stance_target     stance_target NOT NULL,
  stance            stance NOT NULL,
  stance_confidence confidence NOT NULL,
  emphasized        jsonb NOT NULL,
  omitted_vs_others jsonb NOT NULL,
  model             text NOT NULL,
  prompt_version    text NOT NULL,
  schema_version    text NOT NULL,
  UNIQUE (article_id, story_id)
);

CREATE TABLE fact_checks (
  id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  source_id         uuid NOT NULL REFERENCES sources(id),
  url               text UNIQUE NOT NULL,
  claim_reviewed    text NOT NULL,
  rating_original   text,
  rating_normalized text,               -- true | false | misleading | unproven | other
  published_at      timestamptz,
  language          text
);

CREATE TABLE claim_fact_check_matches (
  claim_id         uuid NOT NULL REFERENCES claims(id) ON DELETE CASCADE,
  fact_check_id    uuid NOT NULL REFERENCES fact_checks(id) ON DELETE CASCADE,
  similarity       real NOT NULL,
  verdict          text NOT NULL,       -- same_claim | related | different
  verified_by_llm  boolean NOT NULL,
  PRIMARY KEY (claim_id, fact_check_id)
);

CREATE TABLE story_summaries (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  story_id        uuid NOT NULL REFERENCES stories(id) ON DELETE CASCADE,
  version         int NOT NULL,
  lang            text NOT NULL,
  summary         jsonb NOT NULL,       -- [{text, article_ids, chunk_ids}]
  agreements      jsonb NOT NULL,
  disagreements   jsonb NOT NULL,
  model           text NOT NULL,
  prompt_version  text NOT NULL,
  verifier_result jsonb NOT NULL,
  created_at      timestamptz NOT NULL DEFAULT now(),
  UNIQUE (story_id, version, lang)
);
```

## Users, memory, logs

```sql
CREATE TABLE users (
  id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  created_at        timestamptz NOT NULL DEFAULT now(),
  consent_at        timestamptz,       -- consent to store preferences
  consolidated_at   timestamptz,       -- last memory consolidation (docs/11)
  identity_provider text,              -- 'google' when signed in (ADR-0044)
  identity_hash     text UNIQUE        -- SHA-256 of provider:subject; no email, no name
);

CREATE TABLE ops_flags (               -- operator switches, e.g. the G-OPS-03 kill switch (ADR-0045)
  key         text PRIMARY KEY,        -- 'generation': {"off": bool, "off_topics": [topic, ...]}
  value       jsonb NOT NULL,
  updated_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE user_sessions (           -- one per signed-in browser (ADR-0041, ADR-0044)
  token_hash  text PRIMARY KEY,        -- SHA-256 of the cookie token; the token is never stored
  user_id     uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE user_preferences (        -- semantic memory, strict schema (docs/11)
  user_id     uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  key         text NOT NULL,          -- from fixed enum only
  value       jsonb NOT NULL,
  updated_at  timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (user_id, key)
);

CREATE TABLE story_views (             -- episodic memory
  user_id     uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  story_id    uuid NOT NULL REFERENCES stories(id) ON DELETE CASCADE,
  viewed_at   timestamptz NOT NULL DEFAULT now(),
  story_version_seen int
);

CREATE TABLE ask_turns (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  session_id      uuid NOT NULL,
  user_id         uuid REFERENCES users(id) ON DELETE SET NULL,
  raw_query       text NOT NULL,        -- PII-masked before storage
  neutral_query   text,
  lang            text,
  intent          text,
  story_ids       uuid[],
  answer          jsonb,
  abstained       boolean NOT NULL DEFAULT false,
  model_versions  jsonb,
  prompt_versions jsonb,
  langsmith_run_id text,
  created_at      timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE guard_events (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  run_id      text NOT NULL,
  guard_id    text NOT NULL,           -- e.g. G-GEN-02
  stage       text NOT NULL,
  passed      boolean NOT NULL,
  action      text NOT NULL,
  reason      text,
  score       real,
  meta        jsonb,
  created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ON guard_events (guard_id, created_at DESC);

CREATE TABLE review_queue (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  kind        text NOT NULL,           -- story | ask_turn | rating | cluster
  ref_id      uuid NOT NULL,
  reason      text NOT NULL,
  status      text NOT NULL DEFAULT 'open',
  assigned_to text,
  created_at  timestamptz NOT NULL DEFAULT now(),
  resolved_at timestamptz
);

CREATE TABLE feedback (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  kind        text NOT NULL,           -- wrong_cluster | wrong_stance | wrong_rating | wrong_summary | other
  ref_id      uuid,
  message     text,
  created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE dead_letters (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  stage       text NOT NULL,
  payload     jsonb NOT NULL,
  error       text NOT NULL,
  attempts    int NOT NULL DEFAULT 0,
  created_at  timestamptz NOT NULL DEFAULT now()
);
```

## Qdrant collections

### `chunks`

```python
client.create_collection(
    "chunks",
    vectors_config={
        "dense": models.VectorParams(size=1024, distance=models.Distance.COSINE),
        "colbert": models.VectorParams(
            size=1024,   # BGE-M3 colbert vectors are 1024-d; Jina-ColBERT-v2 is 128-d. Match the model in use.
            distance=models.Distance.COSINE,
            multivector_config=models.MultiVectorConfig(
                comparator=models.MultiVectorComparator.MAX_SIM),
            hnsw_config=models.HnswConfigDiff(m=0),   # rerank only, no graph
        ),
    },
    sparse_vectors_config={"sparse": models.SparseVectorParams()},
)
```

Payload fields: `chunk_id`, `article_id`, `story_id`, `source_id`, `language`, `published_at` (datetime), `is_syndicated`, `stance` (optional), `char_start`, `char_end`.

Create payload indexes on `story_id`, `source_id`, `language`, `published_at`, `is_syndicated`.

The text embedded is `"{outlet} | {date} | {headline}\n{chunk_text}"`. The stored payload text is the **raw chunk text** with no prefix.

**Storage warning:** multivectors cost one vector per token. Keep ColBERT vectors only for a recent window (start at 30 to 60 days), or use a 128-d model, or store float16/quantized, or encode only top candidates at query time. Decide with numbers in Phase 5. See `docs/05_RETRIEVAL.md`.

### `stories`

One point per story. Vectors: `dense` (centroid of article embeddings, updated incrementally) and `sparse` (headline plus summary text). Payload: `story_id`, `topic`, `region`, `status`, `last_updated_at`, `languages`.

### `fact_checks`

Dense vector of `claim_reviewed`. Payload: `fact_check_id`, `source_id`, `language`, `published_at`.

## Lifecycle and retention

- Stories: `developing` while new articles arrive within 24 h, `stable` after, `archived` after 7 days idle (tunable)
- ColBERT vectors are dropped for archived stories. Dense and sparse stay
- `ask_turns` retention: default 30 days, configurable, purge job required (DPDP)
- User deletion cascades to `user_preferences`, `story_views`, and nulls `ask_turns.user_id`
