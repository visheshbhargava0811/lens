# 12 Build plan

Work one phase at a time. A phase is done only when its acceptance criteria pass and evals are recorded. Two tracks run in parallel where possible: backend (A) and frontend (B), joined by the API contract in `docs/09` and MSW fixtures.

Each phase has a **kickoff prompt** you can paste to Claude Code.

## Overview

| Phase | Track | Goal | Depends on |
|---|---|---|---|
| 0 | A + B | Scaffold, infra, CI, tracing wired | none |
| 1A | A | Sources and ingestion | 0 |
| 1B | B | UI shell with fixtures: Home, Story, Blindspot | 0 |
| 2 | A | Chunking, embeddings, clustering, clustering eval | 1A |
| 3 | A + B | Source metadata, coverage stats, blindspots, connect UI to real API | 1B, 2 |
| 4 | A | Claims, framing and stance, cited story summaries | 3 |
| 5 | A | Retrieval stack with ablation | 2 |
| 6 | A + B | Online graph, Ask, guards, SSE, Ask UI | 4, 5 |
| 7 | A | LLM Ops: datasets, judge calibration, CI gate, release flow | 6 (start earlier in parts) |
| 8 | A + B | Fact-check matching, localization, audio | 6 |
| 9 | A + B | Memory and personalization | 8 |
| 10 | A + B | Hardening and launch checklist | all |

**Evals start early.** Start building datasets in Phase 2. Do not wait for Phase 7 to set up LangSmith tracing (Phase 0 wires it).

---

## Phase 0: Scaffold

Tasks
- Create the repo layout from `CLAUDE.md`
- `infra/docker-compose.yml` with Postgres 16, Qdrant, Redis
- Backend: `pyproject.toml` (uv), settings via pydantic-settings, structured logging, FastAPI app with `/health`, SQLAlchemy models and Alembic migrations from `docs/03`
- `config/*.yaml` starters from the docs
- Frontend: Next.js + TypeScript + Tailwind + shadcn/ui, tokens from `docs/10`, empty layout with header, MSW set up
- Makefile with all targets in `CLAUDE.md`
- CI: lint, types, unit tests, frontend build
- LangSmith tracing wired with a trivial traced function
- `docs/DECISIONS.md` created

Acceptance
- `make up && make migrate && make test && make lint` green
- `/health` returns ok, migrations apply cleanly on an empty DB
- Web shell renders with the tokens and fonts in English and Hindi
- A test trace appears in LangSmith

Kickoff prompt
> Read CLAUDE.md and docs/02, docs/03, docs/12. Do Phase 0 only. Restate the plan as a checklist first, then implement. Check current docs for versions of FastAPI, SQLAlchemy, Alembic, Qdrant client, LangGraph, LangSmith, and Next.js, and pin them. Stop when the acceptance criteria pass and summarize what you did.

---

## Phase 1A: Sources and ingestion

Tasks
- Source registry loader from `data/sources/sources.seed.yaml` (`docs/13`). Do **not** fill in ownership or ratings from memory
- Fetcher with per-source intervals, ETag support, robots.txt and `license_mode` enforcement
- Triage: language ID (incl. `hi-Latn`), is_news filter, syndication detection
- Store articles with correct `analysis_depth`
- Arq worker and scheduler, dead-letter handling
- Ingest lag and per-source health metrics

Acceptance
- At least 15 sources across English, Hindi, and one regional language ingest continuously for 48 hours
- Re-running ingestion is idempotent (no duplicate articles)
- No `full_text` stored for `snippet_only` or `link_only` sources (test)
- Language ID accuracy measured on a small labeled sample and recorded
- Syndicated wire copies flagged, with a test on known examples

Kickoff prompt
> Read CLAUDE.md, docs/03, docs/04 (sections 1 and 2), docs/13. Do Phase 1A only. Do not invent RSS URLs or outlet facts: use the TO_VERIFY placeholders and stop to ask me to fill them, or read the sources' sites to find feeds and record the evidence URL.

---

## Phase 1B: UI shell with fixtures (parallel)

Tasks
- Implement tokens, layout, header, bottom tab bar
- Components: CoverageBar, StanceLegend, StoryCard (3 variants), FlagChip, ArticleRow, SummaryBlock, CitationChip, FactualityMeter, OwnershipTags
- Pages: Home, Story, Blindspot, Methodology (static content placeholder), with MSW fixtures matching `docs/09`
- English and Hindi UI strings
- Playwright and axe tests, unit tests for CoverageBar math

Acceptance
- UI acceptance checklist in `docs/10` items for these pages pass at 375, 768, 1280 px
- Fixtures include: normal story, limited coverage, blindspot (stance and language), unrated sources, Hindi headlines, syndicated rows, empty and error states

Kickoff prompt
> Read CLAUDE.md, docs/09, docs/10. Do Phase 1B only. Build against MSW fixtures. Follow the design direction in docs/10 (patterns from Ground News, none of its assets or copy). Use the design plan approach: state your tokens and layout choices briefly, check they match docs/10, then build. Take screenshots at 375, 768, and 1280 px and critique them before finishing.

---

## Phase 2: Chunk, embed, cluster, and clustering eval

Tasks
- Indic-aware sentence splitter and semantic chunker with offsets
- BGE-M3 wrapper producing dense, sparse, multivector. Qdrant collections (`docs/03`)
- Article vectors, incremental assignment, cluster verifier, story lifecycle, nightly batch pass
- Clustering eval runner and labeling export format (`docs/04`)
- Baseline: recursive chunking and dense-only, recorded

Acceptance
- `reports/clustering_baseline.md` with B-cubed F1, ARI, V-measure, cross-lingual pair accuracy, verifier call rate
- Thresholds tuned against the labeled set (or a documented interim set if labels are not ready, clearly marked)
- Stories appear in Postgres with correct counts, languages, lifecycle transitions (tests)

Kickoff prompt
> Read CLAUDE.md, docs/04, docs/05 (chunking and models), docs/08 (clustering section). Do Phase 2 only. First build the eval loader and labeling export, then the baseline, then tune. Tell me how many labeled stories you need from me and in what format.

---

## Phase 3: Source metadata, stats, blindspots, connect UI

Tasks
- `source_ownership` and `source_ratings` import via CSV with required evidence URLs (admin endpoint and CLI)
- `story_stats` computation: stance counts (using a stub stance until Phase 4), factuality, ownership, language, confidence, blindspot detection
- Feed, story, blindspot, source, methodology endpoints per `docs/09`
- Frontend switches from MSW to the real API, fixtures stay for tests
- Methodology page content

Acceptance
- Coverage math unit tests with edge cases (ties, rounding to 100, unclassified, syndication dedup, below `min_sources`)
- API contract tests pass, including the `G-BIAS-01` contract test
- Feed and story pages load real clustered data end to end

Kickoff prompt
> Read CLAUDE.md, docs/01 (stance and blindspots), docs/03, docs/04 (section 11), docs/09. Do Phase 3 only. Stance can be a stub. Everything shown must include confidence and methodology_url.

---

## Phase 4: Claims, framing and stance, story summaries

Tasks
- Entity, claim, framing, and stance nodes with the schemas in `docs/06`, source-masked stance pass, contrastive pass
- Deterministic quote verification (`G-GEN-02`), citation checks (`G-GEN-01`)
- Story summarizer with cited sentences, judge verification (`G-GEN-03`), versioned storage
- Stance rubric skill file, stance eval set and runner, masked-source and symmetry audits
- Sensitive-topic routing to the review queue (`G-OUT-07`)

Acceptance
- Quote-match rate 100% on stored claims (tests)
- Stance macro-F1 baseline recorded per language, masked-source consistency measured
- Faithfulness judge calibrated against human labels (kappa recorded)
- Stories show real stance splits and verified summaries in the UI

Kickoff prompt
> Read CLAUDE.md, docs/04 (sections 6 to 10), docs/06, docs/07 (G-GEN, G-BIAS), docs/08. Do Phase 4 only. Build the eval sets and runners before tuning prompts. Report baseline numbers before any prompt iteration.

---

## Phase 5: Retrieval stack

Tasks
- Two-tier retrieval, hybrid search, RRF, ColBERT rerank, source-balanced selection (`docs/05`)
- Retrieval eval set and runner, ablation report
- Storage strategy for multivectors decided with measurements

Acceptance
- `reports/retrieval_ablation.md` covering all variants in `docs/05`
- Decision entries in `docs/DECISIONS.md` for each component kept or dropped
- Per-outlet coverage in top-k reported, source balancing shown to improve it

Kickoff prompt
> Read CLAUDE.md, docs/05, docs/08. Do Phase 5 only. Verify the Qdrant multivector and query_points APIs against current docs before writing code. Produce the ablation before choosing the final pipeline.

---

## Phase 6: Online graph and Ask

Tasks
- Graph 2 nodes per `docs/06`, router, bounded loops, Postgres checkpointer
- Freshness node with mini pipeline, timeouts, and budgets
- All input, evidence, generation, and output guards (`docs/07`) with `traced_guard`
- `/ask` SSE endpoint with rate limits
- Ask UI, AnswerCard, abstain and sensitive-topic states
- Adversarial set v1 and runner

Acceptance
- Adversarial pass rate at or above the gate, benign false-block rate below the gate
- Every sentence in every test answer is cited, quotes verified
- Abstain path works for no-evidence, out-of-scope, and injection cases
- Every guard appears as a named run in LangSmith with feedback scores
- p95 latency and cost per Ask recorded

Kickoff prompt
> Read CLAUDE.md, docs/05, docs/06, docs/07, docs/09 (`/ask`), docs/10 (Ask page). Do Phase 6 only. Build the linear chain first (query understanding, retriever, synthesis, verifier), verify it, then add the router, freshness, and remaining guards.

---

## Phase 7: LLM Ops

Tasks
- LangSmith datasets for all suites in `docs/08`, `make eval` and reports
- CI gate with `config/eval_gates.yaml`, including a test that a broken prompt fails it
- Judge calibration reports per language
- Online evaluators on sampled traces, annotation queue, promotion of reviewed failures to datasets
- Release flow: versioned prompts, model tier map, retrieval config, staging then canary then prod, one-command rollback

Acceptance
- CI fails on a deliberately degraded prompt
- Annotation queue receives guard failures
- Rollback tested

Kickoff prompt
> Read CLAUDE.md and docs/08. Do Phase 7. Much of the eval scaffolding already exists from earlier phases: consolidate it, do not duplicate it.

---

## Phase 8: Fact-checks, localization, audio

Tasks
- Fact-check ingest (ClaimReview and direct feeds), embedding, matcher with LLM verification (`docs/04`, section 9)
- Fact-check display in Story and Ask, `G-GEN-06`
- Localization node (benchmark IndicTrans2, Bhashini, Sarvam per language), `G-OUT-06`
- Optional audio summaries

Acceptance
- `factcheck_match` eval recorded, precision prioritized over recall
- Post-translation check catches deliberately corrupted entities and numbers (test)
- Translated content labeled in the UI

Kickoff prompt
> Read CLAUDE.md, docs/04 (section 9), docs/06, docs/07 (G-GEN-06, G-OUT-06). Do Phase 8. Benchmark translation options on our own Hindi and one regional-language samples before choosing.

---

## Phase 9: Memory and personalization

Follow `docs/11` exactly.

Acceptance
- All tests in `docs/11` pass, including identical outlet sets across different users
- `/me` view, edit, delete-everything works
- Consent gate enforced

Kickoff prompt
> Read CLAUDE.md and docs/11. Do Phase 9. Do not add any field, prompt, or feature that infers or stores political leaning. If something seems to need it, stop and ask.

---

## Phase 10: Hardening and launch checklist

- [ ] Load test feed, story, and Ask paths. Record capacity and cost
- [ ] Review queue and kill switch tested end to end
- [ ] Legal review of licensing, image use, rating publication, victim and minor handling, election-period handling
- [ ] DPDP: consent, retention purge, deletion, privacy notice
- [ ] Methodology page complete: raters, rubric, validation results, changelog, corrections process
- [ ] Red-team pass with the adversarial set plus fresh cases, including regional-language and Hinglish
- [ ] Monitoring and alerts for ingest lag, guard block spikes, faithfulness drops, cost spikes
- [ ] Secrets in a vault, dependency audit, rate limits verified
- [ ] Backups and restore tested
- [ ] Runbook for incidents (bad summary, wrong cluster, outlet dispute)

Kickoff prompt
> Read CLAUDE.md and docs/07, docs/08, docs/12 (Phase 10). Work through the launch checklist item by item and report status for each. Do not mark legal items done. Flag them for human review.
