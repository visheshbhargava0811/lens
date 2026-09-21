# Lens developer commands. See CLAUDE.md.
SHELL := /bin/bash
COMPOSE := docker compose -f infra/docker-compose.yml
# The repo root holds a stray uv project; make sure backend commands use backend/.venv.
UV := cd backend && env -u VIRTUAL_ENV uv run
NPM := cd frontend && npm

.PHONY: up down migrate seed discover-feeds seed-gen ingest-once ingest-up ingest-logs ingest-health reprocess backend-dev worker frontend-dev frontend-mock test test-backend test-frontend \
        test-e2e lint eval gen-client trace-smoke install

install:
	cd backend && env -u VIRTUAL_ENV uv sync
	$(NPM) ci

up:
	$(COMPOSE) up -d --wait

down:
	$(COMPOSE) down

migrate:
	$(UV) alembic upgrade head

seed:
	$(UV) python -m lens.ingest.registry

# Feed discovery (evidence for sources.seed.yaml) and seed generation. Pass slugs to limit: make discover-feeds ARGS="the-hindu"
discover-feeds:
	$(UV) python -m lens.ingest.discovery $(ARGS)

seed-gen:
	$(UV) python -m lens.ingest.seedgen

# Fetch every active feed once, in-process (no Redis). The worker does this on a schedule.
ingest-once:
	$(UV) python -m lens.ingest.run_once

ingest-up:
	$(COMPOSE) --profile ingest up -d --build worker

ingest-logs:
	$(COMPOSE) --profile ingest logs -f --tail=100 worker

ingest-health:
	$(UV) python -m lens.ingest.health

reprocess:
	$(UV) python -m lens.ingest.reprocess

backend-dev:
	$(UV) uvicorn lens.api.app:app --reload --port 8000

worker:
	$(UV) arq lens.worker.WorkerSettings

frontend-dev:
	$(NPM) run dev

# Frontend on MSW fixtures (fictional data), no backend needed.
frontend-mock:
	cd frontend && NEXT_PUBLIC_API_MOCKING=enabled npm run dev

test: test-backend test-frontend

test-backend:
	$(UV) pytest

test-frontend:
	$(NPM) test

test-e2e:
	$(NPM) run test:e2e

lint:
	$(UV) ruff check .
	$(UV) ruff format --check .
	$(UV) mypy
	$(NPM) run lint
	$(NPM) run typecheck

eval:
	$(UV) python -m lens.evals.langid --write
	$(UV) python -m lens.evals.langid --heldout --write

gen-client:
	$(NPM) run gen-client

# Sends one trace to LangSmith. Needs LANGSMITH_TRACING=true and LANGSMITH_API_KEY in .env.
trace-smoke:
	$(UV) pytest -m live tests/test_tracing.py -rs
