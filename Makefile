# Lens developer commands. See CLAUDE.md.
SHELL := /bin/bash
COMPOSE := docker compose -f infra/docker-compose.yml
# The repo root holds a stray uv project; make sure backend commands use backend/.venv.
UV := cd backend && env -u VIRTUAL_ENV uv run
# Embedding and clustering need the optional ML stack (PyTorch, FlagEmbedding).
UVML := cd backend && env -u VIRTUAL_ENV uv run --extra ml
NPM := cd frontend && npm

.PHONY: index cluster stats eval-summary-ab review pipeline-worker pipeline-up pipeline-logs analyze judge-label-export judge-label-import eval-analysis cluster-label-export cluster-label-import eval-clustering eval-retrieval eval-adversarial topic-prototypes classify-topics eval-topics up down migrate seed discover-feeds seed-gen ingest-once ingest-up ingest-logs ingest-health reprocess backend-dev worker frontend-dev frontend-mock test test-backend test-frontend \
        test-e2e lint eval eval-gate eval-baseline release rollback releases eval-sync eval-promote gen-client trace-smoke install \
        demo-start demo-status demo-serve demo-stop

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

# Phase 7 (docs/08, ADR-0039): run every stale suite, write reports/eval/*.json + reports/eval_<date>.md,
# check the gates. SUITES=topics,langid to pick; FORCE=1 to re-run fresh ones. The ask suite is live.
eval:
	$(UVML) python -m lens.evals.run_all $(if $(SUITES),--suites $(SUITES),) $(if $(FORCE),--force,)

eval-gate:
	$(UV) python -m lens.ops.gate

eval-baseline:
	$(UV) python -m lens.evals.run_all --baseline

# Release flow (docs/08, ADR-0039): pin prompts + config + eval reports under a git tag; roll back in one command.
release:
	$(UV) python -m lens.ops.release create $(NAME)

# Restores the release's prompts/config/reports, re-checks the gate, commits, rebuilds the pipeline image
# (config is baked in). The API reads config per request, so it picks the change up without a restart.
rollback:
	$(UV) python -m lens.ops.release rollback $(TO)
	$(COMPOSE) --profile ingest up -d --build pipeline

releases:
	$(UV) python -m lens.ops.release list

# LangSmith mirrors of data/evals and the review loop (docs/08).
eval-sync:
	$(UV) python -m lens.ops.datasets

eval-promote:
	$(UV) python -m lens.ops.annotation promote
	$(UV) python -m lens.ops.datasets

gen-client:
	$(NPM) run gen-client

# Sends one trace to LangSmith. Needs LANGSMITH_TRACING=true and LANGSMITH_API_KEY in .env.
trace-smoke:
	$(UV) pytest -m live tests/test_tracing.py -rs

# ---- Interview demo (docs/DEMO.md): run locally for a few days, no hosting ----
# demo-start: database, search index, cache, then the news fetcher and the pipeline (every 15 min).
demo-start:
	$(COMPOSE) up -d --wait
	$(MAKE) migrate
	$(MAKE) ingest-up
	$(MAKE) pipeline-up
	@echo ""
	@echo "Lens is collecting news. Check progress any time with: make demo-status"
	@echo "Keep Docker open and the Mac awake and plugged in; start 3-4 days before the demo."

# demo-status: is everything running, and how fresh is the data?
demo-status:
	@docker ps --filter name=lens- --format '{{.Names}}\t{{.Status}}'
	@echo ""
	@docker exec lens-postgres-1 psql -U lens -d lens -At -F ' ' -c "\
	  select 'Newest article fetched:  ' || coalesce(to_char(max(fetched_at) at time zone 'Asia/Kolkata', 'DD Mon HH24:MI') || ' IST', 'none') from articles; \
	  select 'Articles, last 24 h:     ' || count(*) from articles where fetched_at > now() - interval '24 hours'; \
	  select 'Stories updated, 24 h:   ' || count(*) from stories where last_updated_at > now() - interval '24 hours' and source_count >= 2; \
	  select 'AI summaries, 24 h:      ' || count(*) from story_summaries where state = 'published' and created_at > now() - interval '24 hours'; \
	  select 'AI summaries, all time:  ' || count(*) from story_summaries where state = 'published';"

# demo-serve: the API and the website together (Ctrl+C stops both). Open http://localhost:3000
demo-serve:
	@trap 'kill 0' EXIT; \
	  (cd backend && env -u VIRTUAL_ENV uv run uvicorn lens.api.app:app --port 8000) & \
	  (cd frontend && npm run dev) & \
	  wait

# demo-stop: stops everything; all data stays (never add -v, that deletes it).
demo-stop:
	$(COMPOSE) --profile ingest down
	@echo "Stopped. Data is kept. Start again with: make demo-start"
