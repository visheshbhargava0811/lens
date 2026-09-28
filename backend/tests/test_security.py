"""Pre-deploy security checklist (ADR-0042): the controls, each with a failing case."""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from lens.api import limits
from lens.core.settings import Settings

DEPLOYED_OK: dict[str, Any] = {
    "app_env": "prod",
    "database_url": "postgresql+psycopg://app:s3cret@db.internal:5432/lens?sslmode=require",
    "redis_url": "rediss://:s3cret@cache.internal:6380/0",
    "qdrant_api_key": "q" * 32,
    "web_origin": "https://lens.example",
    "admin_token": "a" * 40,
    "rate_limit_salt": "s" * 32,
}


def test_deployed_settings_refuse_dev_defaults_and_weak_secrets() -> None:
    Settings(**DEPLOYED_OK, _env_file=None)
    cases: list[tuple[dict[str, Any], str]] = [
        ({"database_url": "postgresql+psycopg://lens:lens@localhost:5433/lens"}, "DATABASE_URL"),
        ({"redis_url": "redis://localhost:6380/0"}, "REDIS_URL"),
        ({"database_url": "postgresql+psycopg://app:s3cret@db.internal:5432/lens"}, "TLS"),
        ({"qdrant_api_key": None}, "QDRANT_API_KEY"),
        ({"web_origin": "http://lens.example"}, "WEB_ORIGIN"),
        ({"admin_token": "short"}, "ADMIN_TOKEN"),
        ({"rate_limit_salt": None}, "RATE_LIMIT_SALT"),
        ({"log_level": "DEBUG"}, "LOG_LEVEL"),
    ]
    for override, needle in cases:
        with pytest.raises(ValueError, match=needle):
            Settings(**{**DEPLOYED_OK, **override}, _env_file=None)
    Settings(app_env="dev", _env_file=None)  # dev keeps its local defaults


def _app(monkeypatch: pytest.MonkeyPatch, **settings: Any) -> TestClient:
    from lens.api import app as app_module

    s = Settings(**settings, _env_file=None)
    monkeypatch.setattr(app_module, "get_settings", lambda: s)
    return TestClient(app_module.create_app(), raise_server_exceptions=False)


class Counter:
    def __init__(self) -> None:
        self.n: dict[str, int] = {}

    def incr(self, k: str) -> int:
        self.n[k] = self.n.get(k, 0) + 1
        return self.n[k]

    def expire(self, k: str, t: int) -> None: ...

    def ttl(self, k: str) -> int:
        return 42


def test_docs_are_hidden_when_deployed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(limits, "_redis", lambda: Counter())
    assert _app(monkeypatch, app_env="dev").get("/openapi.json").status_code == 200
    prod = _app(monkeypatch, **DEPLOYED_OK)
    for path in ("/docs", "/redoc", "/openapi.json"):
        assert prod.get(path).status_code == 404, path
    assert "max-age" in prod.get("/health").headers["strict-transport-security"]
    from lens.api.routers import health

    monkeypatch.setattr(health, "get_settings", lambda: Settings(**DEPLOYED_OK, _env_file=None))
    assert prod.get("/health").json() == {"status": "ok", "version": None, "env": None}


def test_security_headers_body_limit_and_generic_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(limits, "_redis", lambda: Counter())
    c = _app(monkeypatch)
    h = c.get("/health").headers
    assert h["x-content-type-options"] == "nosniff" and h["x-frame-options"] == "DENY"
    assert h["content-security-policy"] == "default-src 'none'; frame-ancestors 'none'"
    r = c.post("/api/v1/ask", content=b"x" * 2_000_000, headers={"content-type": "application/json"})
    assert r.status_code == 413 and r.json()["error"]["code"] == "payload_too_large"

    from lens.api import app as app_module

    app = app_module.create_app()

    @app.get("/boom")
    def boom() -> None:
        raise RuntimeError("secret internal detail")

    r = TestClient(app, raise_server_exceptions=False).get("/boom")
    assert r.status_code == 500 and "secret" not in r.text and r.json()["error"]["code"] == "internal"


def test_cors_allows_only_the_web_origin(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(limits, "_redis", lambda: Counter())
    c = _app(monkeypatch, web_origin="https://lens.example")
    pre = {"access-control-request-method": "PUT", "access-control-request-headers": "x-lens-client"}
    ok = c.options("/api/v1/me/preferences", headers={"origin": "https://lens.example", **pre})
    assert ok.headers.get("access-control-allow-origin") == "https://lens.example"
    bad = c.options("/api/v1/me/preferences", headers={"origin": "https://evil.example", **pre})
    assert "access-control-allow-origin" not in bad.headers


def test_rate_limits_public_and_admin_before_auth(monkeypatch: pytest.MonkeyPatch, client: Any) -> None:
    counter = Counter()
    monkeypatch.setattr(limits, "_redis", lambda: counter)
    monkeypatch.setattr(
        limits,
        "load_yaml",
        lambda name: {
            "rate_limits": {
                "public": {"rate_per_minute": 2, "rate_per_day": 99},
                "admin": {"rate_per_minute": 1, "rate_per_day": 99},
                "me": {"rate_per_minute": 99, "rate_per_day": 99},
            }
        },
    )
    codes = [client.get("/api/v1/topics").status_code for _ in range(3)]
    assert codes[:2] == [200, 200] and codes[2] == 429
    assert client.get("/api/v1/topics").headers["retry-after"] == "42"
    first = client.get("/api/v1/admin/review-queue", headers={"authorization": "Bearer wrong"})
    assert first.status_code in (401, 503)  # wrong token (or admin disabled)
    second = client.get("/api/v1/admin/review-queue", headers={"authorization": "Bearer wrong"})
    assert second.status_code == 429  # guessing is throttled before the token is even checked


def test_admin_fails_closed_without_redis(monkeypatch: pytest.MonkeyPatch, client: Any) -> None:
    import redis

    class Broken:
        def incr(self, k: str) -> int:
            raise redis.ConnectionError("down")

    monkeypatch.setattr(limits, "_redis", lambda: Broken())
    assert client.get("/api/v1/admin/review-queue").status_code == 503
    assert client.get("/api/v1/topics").status_code == 200  # public reads fail open


def test_control_characters_and_oversized_params_are_refused(client: Any) -> None:
    from lens.schemas.api import AskRequest

    assert client.get("/api/v1/stories/%00abc").status_code == 400  # was a 500 (Postgres rejects NUL)
    assert client.get("/api/v1/feed?topic=a%0Db").status_code == 400
    assert client.get("/api/v1/feed?topic=" + "a" * 300).status_code == 422
    assert client.get("/api/v1/feed?topic=%27%20OR%201%3D1--").status_code == 200  # bound parameter: no match
    assert AskRequest(query="what\x00 happened\x07?").query == "what happened?"
    with pytest.raises(ValueError):
        AskRequest(query="\x00\x01")


def test_only_web_links_are_stored() -> None:
    from lens.factchecks.ingest import reviews
    from lens.ingest.store import web_url

    assert web_url("https://www.thehindu.com/x") and web_url("http://example.org/x")
    for bad in ("javascript:alert(1)", " JavaScript:alert(1)", "data:text/html,x", "", None, "ftp://x/y"):
        assert not web_url(bad), bad
    payload = {
        "claims": [{"text": "c", "claimReview": [{"url": "javascript:alert(1)", "publisher": {"site": "boom.in"}}]}]
    }
    assert list(reviews(payload, ["boom.in"], None)) == []


def test_empty_admin_token_never_opens_admin(monkeypatch: pytest.MonkeyPatch, client: Any, tmp_path: Any) -> None:
    """Regression: `ADMIN_TOKEN=` used to parse as an empty secret, which an empty bearer header matched."""
    env = tmp_path / ".env"
    env.write_text("ADMIN_TOKEN=\nQDRANT_API_KEY=\n")
    s = Settings(_env_file=env)
    assert s.admin_token is None and s.qdrant_api_key is None

    from pydantic import SecretStr

    from lens.api.routers import admin

    monkeypatch.setattr(limits, "_redis", lambda: Counter())
    for token in (None, SecretStr("")):
        monkeypatch.setattr(admin, "get_settings", lambda t=token: Settings(admin_token=t, _env_file=None))
        for header in ({}, {"authorization": "Bearer "}, {"authorization": ""}):
            assert client.get("/api/v1/admin/review-queue", headers=header).status_code in (401, 503)
    monkeypatch.setattr(admin, "get_settings", lambda: Settings(admin_token="t" * 40, _env_file=None))
    assert client.get("/api/v1/admin/review-queue", headers={"authorization": "Bearer "}).status_code == 401
    assert client.get("/api/v1/admin/review-queue", headers={"authorization": "Bearer " + "t" * 40}).status_code == 200


def test_session_tokens_are_stored_only_as_hashes(db: Any) -> None:
    import hashlib

    from sqlalchemy import select

    from lens.db.models import UserSession
    from lens.memory import store

    user = store.sign_in(db, "google", "subject-1")
    raw = store.new_session(db, user)
    stored = db.execute(select(UserSession.token_hash).where(UserSession.user_id == user.id)).scalar_one()
    assert stored != raw and raw not in stored and stored == hashlib.sha256(raw.encode()).hexdigest()
    assert len(raw) >= 40  # 32 random bytes, url-safe
    assert store.user_for_token(db, raw) is not None and store.user_for_token(db, stored) is None
