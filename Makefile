# Lens developer commands. See CLAUDE.md.
SHELL := /bin/bash
COMPOSE := docker compose -f infra/docker-compose.yml
# The repo root holds a stray uv project; make sure backend commands use backend/.venv.
UV := cd backend && env -u VIRTUAL_ENV uv run
# Embedding and clustering need the optional ML stack (PyTorch, FlagEmbedding).
UVML := cd backend && env -u VIRTUAL_ENV uv run --extra ml
NPM := cd frontend && npm

.PHONY: index cluster stats eval-summary-ab review pipeline-worker pipeline-up pipeline-logs analyze judge-label-export judge-label-import eval-analysis cluster-label-export cluster-label-import eval-clustering eval-retrieval eval-adversarial topic-prototypes classify-topics eval-topics up down migrate seed discover-feeds seed-gen ingest-once ingest-up ingest-logs ingest-health reprocess backend-dev worker frontend-dev frontend-mock test test-backend test-frontend \
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

# Phase 2: chunk + embed stored articles into Qdrant, then the clustering eval loop.
index:
	$(UVML) python -m lens.pipeline.index

cluster:
	$(UVML) python -m lens.pipeline.cluster

topic-prototypes:
	$(UV) python -m lens.nlp.topic_embed build

classify-topics:
	$(UV) python -m lens.nlp.topic_embed backfill

eval-topics:
	$(UV) python -m lens.evals.topics --name $(or $(NAME),v1)

# Foreground, for development. The always-on worker is the Docker service: `make pipeline-up`.
pipeline-worker:
	$(UVML) arq lens.pipeline.worker.PipelineSettings

pipeline-up:
	$(UVML) python -c "from huggingface_hub import snapshot_download; snapshot_download('BAAI/bge-m3')"
	$(COMPOSE) --profile ingest up -d --build pipeline

pipeline-logs:
	$(COMPOSE) --profile ingest logs -f --tail=100 pipeline

analyze:
	$(UV) python -m lens.pipeline.analyze $(N)

judge-label-export:
	$(UV) python -m lens.evals.analysis export $(ARGS)

judge-label-import:
	$(UV) python -m lens.evals.analysis import ../$(FILE) --annotator $(ANNOTATOR) --name $(NAME)

eval-analysis:
	$(UV) python -m lens.evals.analysis run --name $(or $(NAME),baseline) $(if $(GOLD),--gold ../$(GOLD),)

review:
	$(UV) python -m lens.services.review $(ARGS)

eval-summary-ab:
	$(UV) python -m lens.evals.summary_ab --n $(or $(N),12)

stats:
	$(UV) python -m lens.pipeline.stats

cluster-label-export:
	$(UVML) python -m lens.evals.clustering_labeling export $(ARGS)

cluster-label-import:
	$(UV) python -m lens.evals.clustering_labeling import ../$(FILE) --annotator $(ANNOTATOR) --name $(NAME)

eval-clustering:
	$(UVML) python -m lens.evals.clustering_run --name $(or $(NAME),baseline) $(if $(GOLD),--gold $(GOLD),)

# Phase 6: Ask adversarial + benign suites, live (resumable; spends LLM quota). ARGS="--limit 20" to batch.
eval-adversarial:
	$(UVML) python -m lens.evals.ask_adversarial --name $(or $(NAME),v1) $(ARGS)

# Phase 5: retrieval ablation (docs/05). QUERIES defaults to queries_v1.jsonl.
eval-retrieval:
	$(UVML) python -m lens.evals.retrieval_run --name $(or $(NAME),v1) $(if $(QUERIES),--queries $(QUERIES),) $(ARGS)

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
