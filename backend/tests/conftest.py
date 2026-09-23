"""Shared fixtures. DB tests run against a throwaway database migrated to head."""

import os

# Tests never talk to LangSmith or any external service (CLAUDE.md: unit tests mock LLM calls).
# Environment variables take precedence over .env in pydantic-settings and in the langsmith SDK.
os.environ["LANGSMITH_TRACING"] = "false"

import uuid
from collections.abc import Iterator

import pytest
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from alembic import command
from lens.api.app import create_app
from lens.core.settings import REPO_ROOT, get_settings
from lens.db.session import get_session


@pytest.fixture(scope="session")
def migrated_engine() -> Iterator[Engine]:
    base = make_url(get_settings().database_url)
    admin = create_engine(base.set(database="postgres"), isolation_level="AUTOCOMMIT")
    name = f"lens_test_{uuid.uuid4().hex[:8]}"
    try:
        with admin.connect() as conn:
            conn.execute(text(f'CREATE DATABASE "{name}"'))
    except Exception as exc:  # pragma: no cover - environment dependent
        pytest.skip(f"Postgres not reachable ({exc.__class__.__name__}); run `make up`")
    url = base.set(database=name).render_as_string(hide_password=False)
    cfg = Config(str(REPO_ROOT / "backend" / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(cfg, "head")
    engine = create_engine(url)
    try:
        yield engine
    finally:
        engine.dispose()
        with admin.connect() as conn:
            conn.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        admin.dispose()


@pytest.fixture
def db(migrated_engine: Engine) -> Iterator[Session]:
    """A session whose work is rolled back after each test."""
    with migrated_engine.connect() as conn:
        trans = conn.begin()
        session = Session(bind=conn, join_transaction_mode="create_savepoint")
        try:
            yield session
        finally:
            session.close()
            trans.rollback()


@pytest.fixture
def client(db: Session) -> Iterator[TestClient]:
    """API client whose requests use the test transaction."""
    app = create_app()
    app.dependency_overrides[get_session] = lambda: db
    with TestClient(app) as c:
        yield c
