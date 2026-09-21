# Lens

An AI news comparison platform for India. It groups coverage of the same story across outlets and languages and shows how each outlet frames it. It also links claims to fact-checks and answers questions with every sentence cited. Lens is a working name.

- **Spec:** `CLAUDE.md` and `docs/01`–`docs/13`
- **Progress:** `docs/STATUS.md`
- **Decisions:** `docs/DECISIONS.md`

## Quick start

```bash
cp infra/.env.example .env      # fill in keys; never commit .env
make install                    # backend (uv, Python 3.12) and frontend (npm)
make up && make migrate && make seed
make frontend-mock              # UI on fictional MSW fixtures at http://localhost:3000
make ingest-up                  # start the ingestion worker (Docker)
make ingest-health              # per-source lag and failures
make test && make lint
```

## Layout

- `backend/`: FastAPI, SQLAlchemy/Alembic, Arq worker, ingestion (`lens.ingest`)
- `frontend/`: Next.js 16, Tailwind, shadcn/ui, next-intl (English and Hindi), MSW fixtures
- `config/`: model tiers, retrieval, clustering, guardrails, ingest, eval gates
- `data/sources/`: candidate outlets, feed-discovery evidence, feed selection, generated seed
- `data/evals/`: eval sets
- `reports/`: eval and review reports
- `infra/`: docker compose (Postgres 16, Qdrant, Redis, worker)

The fixture data in `frontend/src/mocks/` is entirely fictional.
