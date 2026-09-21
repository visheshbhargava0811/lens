# CLAUDE.md

Project: **Lens** (working name, placeholder). An AI news comparison platform for India.

It clusters coverage of the same story across outlets and languages, shows how each outlet frames it, links claims to fact-checks, and answers questions in a chat interface where every sentence is cited. The UI follows the familiar Ground News pattern (story feed, coverage bar, blindspots, per-story source lists), adapted for India.

Read this file at the start of every session. Detailed specs are in `docs/`.

## Read order

| Doc | Read when |
|---|---|
| `docs/STATUS.md` | **Every session, first.** Current phase, what is running, gotchas, open items |
| `docs/01_PRODUCT.md` | Starting anything. Scope, features, India adaptation, open decisions |
| `docs/02_ARCHITECTURE.md` | Touching infra, services, config, or model tiers |
| `docs/03_DATA_MODEL.md` | Touching Postgres or Qdrant |
| `docs/04_INGESTION_AND_CLUSTERING.md` | Building the offline pipeline |
| `docs/05_RETRIEVAL.md` | Building hybrid search, ColBERT rerank, source balancing |
| `docs/06_AGENTS_AND_SCHEMAS.md` | Building either LangGraph graph or any LLM call |
| `docs/07_GUARDRAILS.md` | Building or changing any guard |
| `docs/08_EVALS_LLMOPS.md` | Anything that changes model behavior |
| `docs/09_API_SPEC.md` | Building endpoints or the frontend client |
| `docs/10_UI_SPEC.md` | Building any frontend page or component |
| `docs/11_MEMORY.md` | Building user memory (Phase 9 only) |
| `docs/12_BUILD_PLAN.md` | Deciding what to do next. Work phase by phase |
| `docs/13_INDIA_SOURCES.md` | Seeding sources, ratings, fact-checkers |

## Non-negotiable rules

1. **Every generated sentence is cited.** Summaries and answers carry at least one `article_id` per sentence, enforced in the Pydantic schema (`min_length=1`). Quotes are verified verbatim against stored text by deterministic code before any LLM verifier runs.
2. **Untrusted text stays untrusted.** Article text and user input are data, never instructions. Wrap them in delimiters, never put them in the system prompt, and give synthesis nodes no tools.
3. **Structured output everywhere.** Every LLM call returns a Pydantic model (`with_structured_output` or `instructor`). No regex parsing of free text. Schemas carry a `schema_version`.
4. **Cheapest sufficient tool.** Deterministic code first, small model second, strong LLM last. Model choice comes from `config/models.yaml`, never hard-coded.
5. **No political profiling.** Never infer or store a user's political leaning. Personalization must never change which outlets appear in a coverage comparison.
6. **Licensing is enforced in code.** `sources.license_mode` (`full_text` | `snippet_only` | `link_only`) decides what may be stored and displayed. Default is `snippet_only`. Image use follows `sources.image_policy`.
7. **Ratings need provenance.** Any outlet rating, ownership fact, or stance label is stored with `rater`, `method_url`, `evidence_url`, `retrieved_at`, `confidence`. **Never fill in facts about outlets from memory.** Unknown means null or `TO_VERIFY`, shown in the UI as "Not rated".
8. **Numbers need methodology.** The UI never shows a stance, bias, or factuality figure without a confidence level and a link to the methodology page.
9. **Abstain over guess.** Weak retrieval returns "not enough reliable coverage", not a fluent guess.
10. **Evals before optimization.** No fine-tuning, new retrieval component, or prompt change merges without an eval delta (see `docs/08`).
11. **Library APIs drift.** Before using Qdrant, LangGraph, LangSmith, FlagEmbedding, or new Next.js features, read the current official docs and pin versions in lockfiles. Do not rely on remembered APIs.
12. **Secrets and PII.** No secrets in the repo. PII is masked before anything reaches traces or logs (guard `G-OUT-05`).
13. **Indic text integrity.** Store and quote text in its original script. Never transliterate or translate stored text. Translation happens only in the Localization node and at display time.

## Stack

- **Backend:** Python 3.12, uv, FastAPI, Pydantic v2, LangGraph, LangSmith, SQLAlchemy 2 + Alembic, Postgres 16, Qdrant, Redis + Arq, BGE-M3 via FlagEmbedding, hdbscan, pytest, ruff, mypy
- **Frontend:** Next.js (App Router) + TypeScript, Tailwind, shadcn/ui, TanStack Query, next-intl, MSW for fixtures, Playwright, openapi-typescript
- **Infra:** docker compose for local; deployment target decided in Phase 10

## Repo layout

```
lens/
├── CLAUDE.md
├── Makefile
├── docs/
├── infra/
│   ├── docker-compose.yml        # postgres, qdrant, redis, api, worker, web
│   └── .env.example
├── config/
│   ├── models.yaml               # model tier -> provider/model id
│   ├── retrieval.yaml            # top-k, RRF, balancing
│   ├── clustering.yaml           # thresholds, windows, weights
│   └── guardrails.yaml           # thresholds, sensitive-topic list
├── data/
│   ├── sources/sources.seed.yaml
│   └── evals/                    # jsonl datasets (clustering, retrieval, stance, adversarial, golden)
├── backend/
│   ├── pyproject.toml
│   ├── alembic/
│   ├── src/lens/
│   │   ├── api/                  # routers, SSE
│   │   ├── core/                 # settings, logging, tracing
│   │   ├── db/                   # SQLAlchemy models, repositories
│   │   ├── schemas/              # canonical Pydantic models
│   │   ├── llm/                  # provider clients, tiering, structured-output helpers
│   │   ├── ingest/               # fetchers, extractors, triage
│   │   ├── nlp/                  # language ID, chunking, embeddings, syndication dedup
│   │   ├── clustering/
│   │   ├── retrieval/            # qdrant client, hybrid, colbert rerank, balancing
│   │   ├── agents/
│   │   │   ├── offline/          # LangGraph graph 1
│   │   │   ├── online/           # LangGraph graph 2
│   │   │   └── skills/           # procedural memory: versioned *.md prompt files
│   │   ├── guardrails/
│   │   ├── memory/
│   │   └── evals/
│   └── tests/
└── frontend/
    ├── package.json
    ├── src/app/                  # App Router pages
    ├── src/components/
    ├── src/lib/                  # generated API client, i18n
    ├── src/mocks/                # MSW fixtures matching docs/09
    └── tests/
```

## Commands (create these in Phase 0)

```
make up            # docker compose up -d (postgres, qdrant, redis)
make down
make migrate       # alembic upgrade head
make seed          # load data/sources/sources.seed.yaml
make backend-dev   # uvicorn with reload
make worker        # arq worker
make frontend-dev  # next dev
make test          # pytest + frontend unit tests
make lint          # ruff, mypy, eslint, tsc
make eval          # run offline eval suites, write reports/
make gen-client    # regenerate TS client from OpenAPI
```

## Workflow

- Work **one phase at a time** from `docs/12_BUILD_PLAN.md`. Do not start the next phase until the current acceptance criteria pass.
- At the start of a phase, restate the plan as a short checklist, then implement.
- Write tests with the code. Anything touching clustering, retrieval, generation, or guards also adds or updates eval cases.
- Unit tests mock LLM calls. Tests that hit real models are marked `@pytest.mark.live`.
- Small commits with conventional messages (`feat:`, `fix:`, `test:`, `docs:`, `chore:`).
- If a spec is ambiguous or conflicts with another, ask. Record decisions in `docs/DECISIONS.md` (short ADR entries).
- Build the frontend against `docs/09_API_SPEC.md` using MSW fixtures so UI work is never blocked on the backend.

## Code conventions

- Type hints everywhere, `mypy --strict` on `lens.schemas`, `lens.guardrails`, `lens.retrieval`.
- No business logic in routers. Routers call services, services call repositories.
- Every LangGraph node is a pure function of state plus injected dependencies, with a timeout and a named LangSmith run.
- Every guard returns a `GuardResult` and is wrapped with `traced_guard` (see `docs/07`).
- Config through `pydantic-settings` and the YAML files in `config/`. No magic numbers in code.
- Thresholds in the docs are **starting values**. Tune them on the eval sets and record the result.

## Definition of done (any task)

- Tests pass, lint and types clean
- Relevant evals run, and results are compared to the last baseline
- New LLM calls have a Pydantic schema, a LangSmith trace name, and a mock for tests
- New guards have a failing-case test and appear in `docs/07` with an ID
- Docs updated if behavior or interfaces changed
