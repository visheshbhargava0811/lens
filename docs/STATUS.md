# Project status

The working state of the build: what is done, what is running, and what is known to be broken or open. Update it at the end of every phase or work session. For why decisions were made, see `docs/DECISIONS.md`.

_Last updated: 2026-09-23_

## Phases

| Phase | State | Notes |
|---|---|---|
| 0 Scaffold | Done | `make up && make migrate && make test && make lint` green. The LangSmith smoke trace is verified (`make trace-smoke`) |
| 1B UI shell with fixtures | Done | Home, Story, Blindspot and Methodology pages on MSW fixtures, English and Hindi. Review: `reports/phase1b_ui_review.md`. ADR-0008 accepted. Redesigned in a Ground News tone (ADR-0017, `DESIGN.md`) |
| 1A Sources and ingestion | Done | 24 h acceptance run (ADR-0016) passed 2026-09-22 22:42 UTC: all 17 sources ingested new articles in the window (22 to 6,915 each), 1,947 jobs completed and 0 failed, 0 dead letters. Amar Ujala had 2 "payload is not a feed" errors but still ingested 2,503 articles |
| 2 Chunk, embed, cluster | Done (pending second-annotator check) | Gold set `data/evals/clustering/gold_v1.jsonl`: 436 articles, 211 stories (93 cross-lingual, 16 hard-negative groups with 42 stories, 29 developing), labeled by the owner 2026-09-23 from `to_label_20260922.csv` (raw: `labeled_20260922_raw.csv`; cleaned: `labeled_20260922_v1.csv`, which drops rows 18-19 and clears hard-negative tags used on only one story). Baseline `reports/clustering_baseline.md`: docs thresholds B³ F1 0.82, cross-lingual recall 0.40; tuned on half A (high 0.72, low 0.62) B³ F1 0.99 on held-out half B. **Optimistic:** the gold set started from the clusterer's own draft groups and only 2 rows changed. On all data the tuned config makes 8 hard-negative merges and has 0.76 cross-lingual precision. Tuned thresholds are in `config/clustering.yaml`. `make cluster` has been run on all indexed articles |
| 3 Source metadata, stats, UI | Done | Coverage bar is **outlet-level Left / Center / Right** from Media Bias/Fact Check (ADR-0020, owner decision, replacing article-level government stance). Stats (`lens.stats`, `make stats`), provenance-checked CSV import (CLI and `POST /api/v1/admin/sources/import`), and public endpoints for feed, stories, articles, blindspots, topics, sources and methodology, with contract and `G-BIAS-01` tests. The frontend runs on the real API: the TS client is generated (`make gen-client`) and the fixtures are typed against it. The methodology page shows live thresholds and raters. Checked on real data: feed, story (bias, factuality, ownership), blindspots, methodology |

## What is running

- `make up`: Postgres on 5433, Redis on 6380, Qdrant on 6333. Compose project name: `lens`.
- `make ingest-up`: the `worker` container (Arq). It polls 22 feeds for 17 active sources every 15 minutes and restarts on its own. Poll cadence was fixed 2026-09-23: before that, each feed was fetched about hourly, because arq's stored results blocked re-enqueueing the fixed `_job_id` (now `keep_result = 0`). Logs: `make ingest-logs`.

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
- **Ownership:** all 17 outlets, from `data/sources/source_meta.csv` (owner-verified, with evidence URLs). **Factuality:** MBFC for 11 of 17 outlets (ADR-0019). **Not filled in (rule 7):** terms.

## Gotchas learned the hard way

- **Root folder:** it has a leftover `uv init` project (root `pyproject.toml`, `src/news`, `.venv` on Python 3.13). It is git-ignored. Run backend commands through the Makefile or with `env -u VIRTUAL_ENV uv run` inside `backend/`. Never let uv add `backend` as a workspace member.
- **Indic text:** Python's `\w` and `str.isalpha` exclude Indic vowel signs and viramas. Tokenizers and script counters must include combining marks (ADR-0014, ADR-0015).
- **Dainik Bhaskar timestamps:** its sitemap labels India time as UTC ("…Z"). `sanitize_published_at` corrects this.
- **Hindustan:** `api.livehindustan.com` disallows all crawling in its `robots.txt`, so the www news sitemap is used. Check `robots.txt` on the feed's host, not the homepage's.
- **Node:** runs as x64 under Rosetta. If Vitest can't find rolldown's native binding, regenerate `frontend/package-lock.json`.
- **Next.js 16:** read `frontend/node_modules/next/dist/docs/` before writing Next code. `middleware` is now `proxy`.
- **Root `.env`:** it uses `KEY = value` with spaces, so never `source` it in a shell: the spaces make each line run as a command, and the errors print the secrets. Read keys with a parser (`pydantic-settings` or a regex).
- **Arq job ids:** a fixed `_job_id` cannot be re-enqueued while that job's stored result exists. The worker sets `keep_result = 0` for this reason.
- **LangSmith:** per-fetch tracing is off (`INGEST_TRACE`), because at 20 sources it would use about 2k traces a day.

## Open items needing the owner

- Clustering gold set: a second person should label a 20% sample so we can measure agreement. It would show how optimistic the 0.99 score is.
- Same-outlet duplicates: 45 were stored before the 2026-09-23 fix (same source, same `content_hash`, a new URL within 6 h). They were left in place; new ones are skipped (`fetch.same_source_dup_hours`).
- Ownership: all 17 outlets imported 2026-09-23 (`data/sources/source_meta.csv`). 16 are owner-verified (PRGI links confirmed by the owner). Sakal comes from esakal.com's privacy policy and footer ("Sakal Media Pvt. Ltd.", Sakal Media Group, medium confidence); the owner's CSV had "Sakal Papers Private Limited" with a dead link, so the owner should confirm. Factuality: Media Bias/Fact Check ratings imported for 11 outlets (`data/sources/source_ratings_mbfc.csv`, ADR-0019). The six Indian-language papers have no MBFC page and show "Not rated"; an Indian rater that covers them is still needed.
- Review ADR-0018 (`feed_min_sources: 2`, shapes for `/sources` and `/methodology`) and ADR-0020 (bias mapping: Left-Center counts as Left and Right-Center as Right; no outlet is Center today; the six Indian-language papers are unrated).
- Hindi copy for the bias labels (वाम / मध्य / दक्षिण झुकाव) needs a native review.
- The JS budget is over target (about 163 KB gzipped vs 150).
