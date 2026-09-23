# Decisions

Short ADR entries. Newest last. Format: context, decision, consequences.

## ADR-0001: Open-decision defaults accepted for the MVP (2026-09-21)

- Context: `docs/01_PRODUCT.md` lists open decisions with defaults.
- Decision: Use the defaults until the owner says otherwise: name "Lens" (placeholder); launch languages English and Hindi; portfolio project first; headlines, snippets and links only; text-only tiles; anonymous browsing; no payments.
- Consequences: `sources.license_mode` defaults to `snippet_only`; `image_policy` to `none`.

## ADR-0002: Pinned versions for Phase 0 (2026-09-21)

- Backend (Python 3.12, locked in `backend/uv.lock`): FastAPI 0.141.1, SQLAlchemy 2.0.54, Alembic 1.20.0, psycopg 3.3.6, Pydantic 2.13.5, pydantic-settings 2.15.0, qdrant-client 1.19.1, LangGraph 1.2.12, LangSmith 0.13.0, Arq 0.28.0, structlog 26.1.0.
- Frontend (locked in `frontend/package-lock.json`): Next.js 16.3.5, React 19.2.8, next-intl 4.14.6, TanStack Query 5.103.2, MSW 2.15.0, shadcn CLI 4.21.0 (base-nova), Vitest 5.0.1, Playwright 1.63.0.
- Infra images: `postgres:16-alpine`, `qdrant/qdrant:v1.18.0`, `redis:7-alpine`.
- Not yet added: FlagEmbedding, hdbscan (Phase 2). Check their current docs then.

## ADR-0003: UI language from a cookie, not URL prefixes (2026-09-21)

- Context: docs/10 routes are `/`, `/story/[slug]` etc. with a language switcher that changes UI and summary language.
- Decision: next-intl without i18n routing. Locale is read from the `NEXT_LOCALE` cookie, set by a server action. No `proxy.ts` (Next 16's replacement for `middleware.ts`).
- Consequences: Story URLs are language-neutral and shareable. If SEO for Hindi pages matters later, revisit with `/hi/...` prefixes.

## ADR-0004: Surrogate key on `story_views` (2026-09-21)

- Context: The reference DDL for `story_views` has no primary key; the ORM requires one.
- Decision: Add `id uuid PRIMARY KEY DEFAULT gen_random_uuid()`. All other columns match docs/03.

## ADR-0005: Local ports (2026-09-21)

- Context: A developer machine may already run Postgres on 5432 and Redis on 6379.
- Decision: docker compose publishes Postgres on 5433 and Redis on 6380. Qdrant keeps 6333/6334. Defaults in `lens.core.settings` and `infra/.env.example` match.

## ADR-0006: Fonts for launch languages only (2026-09-21)

- Decision: Load Noto Sans (Latin) and Noto Sans Devanagari via `next/font/google` now. Add other Noto script families when their language launches, to keep page weight down on mobile.

## ADR-0007: Fixtures are fictional and served inside the Next server (2026-09-21)

- Context: Pages are server-rendered (docs/10), so a browser-only MSW worker can't mock their data. Rule 7 forbids outlet facts from memory.
- Decision: `src/instrumentation.ts` starts MSW's node server when `NEXT_PUBLIC_API_MOCKING=enabled`; Playwright and local mock runs set it. Every outlet, owner, rater, fact-checker and event in `src/mocks/fixtures.ts` is invented. Coverage numbers are derived from the article rows with the same `lib/coverage.ts` math the UI uses.
- Consequences: Fixture types are hand-written from docs/09 until Phase 3 generates them from the backend's Pydantic models.

## ADR-0008: `confidence` on story-level `factuality` (2026-09-21) — accepted by owner 2026-09-22

- Context: G-BIAS-01 requires a confidence label on every factuality figure, but the docs/09 `StoryCard.factuality` example has only counts and `methodology_url`.
- Decision: Add `factuality.confidence` (`low | medium | high`). Additive; nothing else in the shape changes.
- Consequences: The backend must emit it in Phase 3. docs/09 amended.

## ADR-0009: Envelope shapes not fixed by docs/09 (2026-09-21)

- `/feed`: `{ items: StoryCard[], next_cursor }`. `/stories/{id}/articles`: `{ items: ArticleRow[], methodology_url }` (the methodology link satisfies G-BIAS-01 for per-article stance). `/blindspots`: `{ type, items, methodology_url }`. `/topics`: `{ items: [{ slug, name }] }`.
- `/stories/{id}` accepts the story id or its slug, so story URLs can use slugs without an extra lookup.

## ADR-0010: Citation chips open a popover first (2026-09-21)

- Context: docs/10 says activating a chip scrolls to the ArticleRow and shows a popover. Scrolling moves the chip, and the popover is anchored to the chip, so doing both at once hides one of them.
- Decision: Activating a chip opens the popover (source, original-language headline, link). Its "Show in source list" button clears filters, scrolls to, highlights and focuses the row.
- Passages are not shown yet: the StoryDetail shape has no passage text and the default `license_mode` is `snippet_only`.

## ADR-0011: Coverage-card placement on the story page (2026-09-21)

- Decision: The coverage card renders twice, under the headline below 1024 px and in the sticky rail above it; the hidden copy is `display: none`. This keeps DOM order equal to visual order for screen readers and keyboard users, which a CSS `order` or `display: contents` layout would break.

## ADR-0012: Phase 1A schema additions and launch sources (2026-09-21)

- **Schema additions (outside the docs/03 DDL):**
  - `source_fetch_state` table: per-feed ETag / Last-Modified, schedule, failure count and last error.
  - `sources.inactive_reason` and `sources.evidence`.
  - `articles.is_opinion`: docs/04 says to keep opinion flagged and exclude it from the coverage bar.
- **Sources:** 20 outlets named by the owner. The feeds come from `make discover-feeds`, which reads each outlet's own site and records evidence in `data/sources/discovery.json`. The choices are in `data/sources/feed_selection.yaml`, and `make seed-gen` writes the seed from both files.
- **Active: 17 outlets.** 10 English, 5 Hindi and 2 Marathi (Sakal, Loksatta).
- **Inactive:**
  - NDTV, Business Standard and The Telegraph return 403 even for `robots.txt`.
  - News18 refuses our crawler by name, and its `robots.txt` bans AI crawlers.
  - The Wire and Lokmat have no feed or news sitemap.
- **Regional language:** Marathi, chosen by the owner for Phase 1A. docs/13 says the launch regional language is confirmed after the Phase 2 baseline.
- **Not recorded anywhere:** ownership, ratings and terms. They stay empty or `TO_VERIFY` (rule 7).

## ADR-0013: Crawling etiquette (2026-09-21)

- The crawler identifies itself as `LensBot/0.1`. It never spoofs a browser and never works around a 403 or a bot block. A blocked outlet needs permission, a licence, or a licensed news API.
- `robots.txt` is checked when a feed is fetched, on the feed's own host. Cache TTL is in `config/ingest.yaml`.
  - A missing file (404/410) means no restrictions (RFC 9309).
  - 401/403, 5xx and network errors mean disallowed.
- **Feed kinds:** RSS/Atom and Google News sitemaps (docs/04 allows sitemaps). Sitemap items carry headlines only, so their `analysis_depth` is `headline_only`.
- **Politeness:** at most 4 feeds in flight, a 15-minute default interval, and exponential backoff capped at 6 hours. After 5 consecutive failures a feed gets one `dead_letters` row.

## ADR-0014: Syndication detection (2026-09-21)

- A wire marker in the byline or dateline sets `syndicated_from`. In a byline, short acronyms such as PTI or ANI count only on their own, in parentheses, or in "with inputs from X", so a reporter named "Ani" isn't taken for ANI.
- **Near-duplicates:** unigram SimHash is a pre-filter (at most 16 bits apart), and word-set Jaccard of at least 0.75 confirms. The window is 72 hours and the other copy must come from a different source. SimHash alone can't separate short headlines: one added word moved a 14-word headline 9 bits.
- **Tokenizing:** words must include Indic combining marks. A first version split Hindi and Marathi words at their vowel signs and linked dozens of unrelated stories. A regression test now covers this.
- The earliest copy is the original. Later copies point to it through `original_article_id`, so stats count a wire story once.

## ADR-0015: Language ID (2026-09-21)

- Unicode script decides first. For Hindi vs Marathi, a function-word and suffix vote decides next, and lingua only breaks a tie. English vs romanized Hindi (`hi-Latn`) uses a function-word list with the English collisions removed.
- The language the feed declares breaks a Hindi/Marathi tie only, never overriding the text.
- **Results:**
  - Held-out accuracy 0.97 (`reports/langid_baseline.md`).
  - `hi-Latn` is 0.80. Revisit it in Phase 6 with the `query_understanding` model.
  - The labels were written by Claude and checked by the owner (native Hindi speaker) on 2026-09-22: all 160 non-English labels confirmed (`data/evals/langid/review_v1.csv`).
  - Code-mixed headlines are labeled by their main language. 53 of 130 Hindi/Marathi rows contain English words ("Lucknow News …", "JSSC-CGL"); all 53 are classified correctly.

## ADR-0016: Phase 1A soak run shortened to 24 hours (2026-09-22) — owner decision

- Context: The Phase 1A acceptance asked for 48 hours of continuous ingestion. The owner wants to unblock Phase 2 labeling sooner.
- Decision: 24 hours of continuous ingestion is enough for acceptance. It still covers a full day-night publishing cycle and every source's schedule at least once.
- Consequences: Multi-day failures (feeds breaking on the second day, slow memory leaks, weekend-only issues) may not show up before acceptance. The worker keeps running after acceptance, so check `make ingest-health` again before the Phase 2 baseline. The clock counts from the worker container's start, 2026-09-21 22:38 UTC.

## ADR-0017: Visual redesign in a Ground News tone (2026-09-22) — owner request

- Context: The owner found the Phase 1B UI generic ("looks AI generated") and asked for a look close in tone to Ground News.
- Decision: Newsprint-grey ground, near-black ink, flat tinted panels, squared corners, Noto Sans 800 headlines, a dark date/language strip, and a flat stance bar with labels set inside the segments. Stance colors stay violet/teal with patterns (no party colors). Only interaction patterns are borrowed, never Ground News assets or exact colors (docs/10). The design system is recorded in `DESIGN.md`; product context in `PRODUCT.md`.
- Consequences: Line heights stay at the docs/10 values. Compact story cards now show confidence and a methodology link like every other card. The rail heading "Topics to follow" became "Browse topics" until following exists. Nav links to unbuilt routes (For you, Local, Ask, Search, Sign in) still 404; the owner decides whether to hide them or add placeholders.

## ADR-0018: Phase 3 stats rules and API shapes not fixed by the docs (2026-09-23) — proposed, owner to review

- **Superseded in part by ADR-0020:** the stance, coverage-confidence and stance-blindspot rules below were replaced by outlet bias. The feed, sources, methodology and admin decisions still stand.

- Context: docs/01 and docs/04 §11 define stats and blindspots loosely ("near-zero", "based on source count…"). docs/09 names `/sources`, `/sources/{id}` and `/methodology` without shapes.
- Decision (stats, all starting values in `config/guardrails.yaml`, tested in `tests/test_stats_coverage.py`):
  - One stance per distinct source: the most common medium- or high-confidence article stance. A tie, low confidence, `not_applicable` or no stance all count as `unclassified`.
  - A syndicated copy is dropped only when its original is in the same story, so a source is never lost because the original sits elsewhere.
  - Coverage confidence is `low` when more than 50% of sources are unclassified or the average stance confidence is below medium. It is `high` with 10+ sources and at most 20% unclassified, and `medium` otherwise.
  - Factuality confidence depends on the rated share of sources: 80% or more is `high`, 50% or more is `medium`, anything else is `low` (ADR-0008).
  - Stance blindspot: at least 70% of *classified* sources in one bucket, with at least `min_sources_for_blindspot` (6) classified sources. Language blindspot: at least 90% of 6+ sources in one group (`en` vs `indic`). Stance wins if both apply.
  - Feed and blindspot lists hide stories with fewer than `feed_min_sources` (2) sources. Otherwise single-article stories (about 78% of the 2026-09-23 data) would flood the feed. Story pages still resolve for them.
- Decision (API): `/sources` → `{ items: SourceSummary[] }`; `/sources/{id|slug}` → `{ source, ownership[], ratings[], recent_stories, methodology_url }`, with every provenance field shown. `/methodology` serves the live parameters and the list of raters; the prose stays in the translated UI messages. `POST /admin/sources/import` takes the CSV as a raw `text/csv` body (no `python-multipart` dependency) with `Authorization: Bearer $ADMIN_TOKEN`. Admin is disabled when `ADMIN_TOKEN` is unset. Any invalid row rejects the whole file.
- Consequences: Until Phase 4 stance lands, every story shows 100% unclassified, `low` confidence and no stance blindspots. That is intended; the UI must not suggest otherwise. Thresholds are to be tuned once stance exists.

## ADR-0019: Media Bias/Fact Check as the first factuality rater (2026-09-23) — owner decision

- Context: Factuality needs a third-party rater with a published method (rule 7, docs/13). The owner chose Media Bias/Fact Check (MBFC).
- Decision: Ratings were read from each outlet's MBFC page (`data/sources/source_ratings_mbfc.csv`), matched only when the page names the outlet's own domain. `method_url` is MBFC's methodology page and `evidence_url` is the outlet's page. Confidence is `high` if the page was updated within 2 years and `medium` otherwise. MBFC covers 11 of the 17 outlets; Dainik Jagran, Dainik Bhaskar, Amar Ujala, Hindustan, Sakal and Loksatta have no MBFC page and stay "Not rated". MBFC's "Mostly Factual" counts in the Mixed bucket on story cards (owner's conservative choice, `stats.factuality_value_map`). Article rows show the exact MBFC wording, as "According to Media Bias/Fact Check".
- Consequences: The six Indian-language outlets are never rated, so factuality confidence stays low on stories dominated by Hindi or Marathi coverage. That is honest, but it skews against those languages; an Indian rater that covers them should be added when one is found. MBFC pages age: re-check them before launch.

## ADR-0020: Outlet-level Left / Center / Right replaces article-level government stance (2026-09-23) — owner decision

- Context: docs/01 had the coverage bar count distinct outlets by each *article's* stance toward the government (critical / balanced / supportive), computed by an LLM in Phase 4, and kept outlet labels off story cards. The owner clarified that the bar should work like Ground News: outlets are Left, Center or Right, and the bar shows which sides covered a story.
- Decision: The bar counts distinct outlets (after syndication dedup) by their **outlet-level bias rating** from a named third-party rater. That rating is stored in `source_ratings` with `dimension = bias` and full provenance (rule 7). The first rater is Media Bias/Fact Check (ADR-0019). Its wording maps to buckets in `config/guardrails.yaml` (`bias_value_map`): Left-Center counts as Left and Right-Center as Right (the Ground News grouping), Least Biased counts as Center, and unknown wording is unrated. Confidence is the rated share of outlets (80% or more is high, 50% or more is medium). A bias blindspot needs at least 70% of 6+ *rated* outlets on one side. The API changed: bucket keys are `left | center | right`, `unrated` replaces `unclassified`, `basis` is `outlet_bias`, blindspot and filter `type` is `bias`, and article rows carry `bias` (bucket) and `source_bias` (the rater's wording and method link) instead of `stance`. `story_stats.stance_counts` was renamed to `bias_counts` (migration 5b1a9c2e7d10).
- Consequences: MBFC rates 11 of 17 outlets, all as Left-Center or Right-Center, so no outlet is Center today. The six Hindi and Marathi papers are unrated, so stories carried mostly by them show a mostly grey bar with low confidence. MBFC's scale comes from US politics, which was the concern docs/01 raised; its fit to Indian outlets is unvalidated. Phase 4 no longer needs an article-stance classifier for the bar. The framing analysis (the `framings` table) can still add per-article context later, but it must not feed the bar without a new ADR. G-BIAS-02/03 (masked-source and symmetry audits) applied to the stance classifier and need re-scoping for Phase 4.
