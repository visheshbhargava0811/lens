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

## ADR-0008: `confidence` on story-level `factuality` (2026-09-21) — needs owner sign-off

- Context: G-BIAS-01 requires a confidence label on every factuality figure, but the docs/09 `StoryCard.factuality` example has only counts and `methodology_url`.
- Decision: Add `factuality.confidence` (`low | medium | high`). Additive; nothing else in the shape changes.
- Consequences: The backend must emit it in Phase 3. docs/09 should be amended if accepted.

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
  - The labels were written by Claude and still need a person to check them.
