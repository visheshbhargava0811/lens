# Backend image (API and worker). Build context is the repo root: config/ and data/sources/ are needed.
FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.12.3 /uv /usr/local/bin/uv

ENV UV_PROJECT_ENVIRONMENT=/app/.venv UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy PYTHONUNBUFFERED=1
WORKDIR /app/backend

COPY backend/pyproject.toml backend/uv.lock backend/.python-version ./
RUN uv sync --locked --no-dev --no-install-project
COPY backend/ ./
RUN uv sync --locked --no-dev

# settings.REPO_ROOT resolves to /app, so keep the repo layout.
COPY config/ /app/config/
COPY data/sources/ /app/data/sources/

ENV PATH=/app/.venv/bin:$PATH
RUN useradd --create-home lens && chown -R lens /app
USER lens
CMD ["arq", "lens.worker.WorkerSettings"]
