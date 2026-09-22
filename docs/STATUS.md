# Project status

The working state of the build: what is done, what is running, and what is known to be broken or open. Update it at the end of every phase or work session. For why decisions were made, see `docs/DECISIONS.md`.

_Last updated: 2026-09-21_

## Phases

| Phase | State | Notes |
|---|---|---|
| 0 Scaffold | Done | `make up && make migrate && make test && make lint` green. The LangSmith smoke trace is verified (`make trace-smoke`) |
| 1B UI shell with fixtures | Done | Home, Story, Blindspot and Methodology pages on MSW fixtures, English and Hindi. Review: `reports/phase1b_ui_review.md`. ADR-0008 accepted. Redesigned in a Ground News tone (ADR-0017, `DESIGN.md`) |
| 1A Sources and ingestion | Built. 24 h acceptance run in progress (ADR-0016) | Worker container (re)started 2026-09-21 22:38 UTC. Confirm with `make ingest-health` after 2026-09-22 22:38 UTC |
| 2 Chunk, embed, cluster | Implementation underway; eval blocked on human labels | Chunking, BGE-M3 wrapper, Qdrant indexing, incremental clustering, lifecycle, merge proposals, and labeling import/export are locally verified. After Phase 1A is accepted, export 100+ stories for human labeling, then run and record the baseline. |

## What is running

- `make up`: Postgres on 5433, Redis on 6380, Qdrant on 6333. Compose project name: `lens`.
- `make ingest-up`: the `worker` container (Arq). It polls 22 feeds for 17 active sources every 15 minutes and restarts on its own. Logs: `make ingest-logs`.

## Sources (ADR-0012, ADR-0013)

- **Active: 17.**
  - English (10): Times of India, The Hindu, Indian Express, Hindustan Times, India Today, Republic, ThePrint, Scroll, Economic Times, Deccan Herald.
  - Hindi (5): Aaj Tak, Dainik Bhaskar, Dainik Jagran, Amar Ujala, Hindustan.
  - Marathi (2): Sakal, Loksatta.
- **Inactive:**
  - NDTV, Business Standard and The Telegraph return 403 even for `robots.txt`.
  - News18 refuses our crawler by name and its `robots.txt` bans AI crawlers.
  - The Wire and Lokmat publish no feed or sitemap.
  - Options: publisher permission, a licence, or a licensed news API (`NEWS_API_KEYS`). Never spoof the user agent.
- **Pipeline:** `candidates.yaml` → `make discover-feeds` → `discovery.json` (evidence) → `feed_selection.yaml` → `make seed-gen` → `sources.seed.yaml` → `make seed`.
- **Not filled in (rule 7):** ownership, ratings and terms.

## Gotchas learned the hard way

- **Root folder:** it has a leftover `uv init` project (root `pyproject.toml`, `src/news`, `.venv` on Python 3.13). It is git-ignored. Run backend commands through the Makefile or with `env -u VIRTUAL_ENV uv run` inside `backend/`. Never let uv add `backend` as a workspace member.
- **Indic text:** Python's `\w` and `str.isalpha` exclude Indic vowel signs and viramas. Tokenizers and script counters must include combining marks (ADR-0014, ADR-0015).
- **Dainik Bhaskar timestamps:** its sitemap labels India time as UTC ("…Z"). `sanitize_published_at` corrects this.
- **Hindustan:** `api.livehindustan.com` disallows all crawling in its `robots.txt`, so the www news sitemap is used. Check `robots.txt` on the feed's host, not the homepage's.
- **Node:** runs as x64 under Rosetta. If Vitest can't find rolldown's native binding, regenerate `frontend/package-lock.json`.
- **Next.js 16:** read `frontend/node_modules/next/dist/docs/` before writing Next code. `middleware` is now `proxy`.
- **LangSmith:** per-fetch tracing is off (`INGEST_TRACE`), because at 20 sources it would use about 2k traces a day.

## Open items needing the owner

- A person to check the language-ID labels in `data/evals/langid/`.
- After the Phase 1A acceptance run: export and label 100+ clustering stories (including 30 cross-lingual, 20 hard-negative, and 10 developing stories), then run the Phase 2 baseline.
- The JS budget is over target (about 163 KB gzipped vs 150).
