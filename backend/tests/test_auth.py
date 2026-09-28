"""Google sign-in (ADR-0044): the OIDC code flow, least data, account linking, sessions per browser."""

from __future__ import annotations

import base64
import hashlib
import time
from datetime import UTC, datetime
from typing import Any
from urllib.parse import parse_qs, urlsplit

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from lens.api.routers import auth, me
from lens.core.settings import Settings
from lens.db.models import User, UserSession
from lens.memory import store

CLIENT_ID = "lens-test.apps.googleusercontent.com"
WEB = "http://localhost:3000"
WRITE = {"X-Lens-Client": "web"}


@pytest.fixture(autouse=True)
def google_on(monkeypatch: pytest.MonkeyPatch) -> None:
    s = Settings(google_client_id=CLIENT_ID, google_client_secret="secret", web_origin=WEB, _env_file=None)
    monkeypatch.setattr(auth, "get_settings", lambda: s)
    monkeypatch.setattr(me, "get_settings", lambda: s)


def claims(sub: str = "1234567890", **over: Any) -> dict[str, Any]:
    return {"iss": "https://accounts.google.com", "aud": CLIENT_ID, "exp": time.time() + 300, "sub": sub, **over}


def sign_in(client: TestClient, monkeypatch: pytest.MonkeyPatch, sub: str = "1234567890", next: str = "/me") -> Any:
    start = client.get(f"/api/v1/auth/google/start?next={next}", follow_redirects=False)
    q = parse_qs(urlsplit(start.headers["location"]).query)
    got = claims(sub, nonce=q["nonce"][0])
    monkeypatch.setattr(auth, "exchange", lambda code, verifier: got)
    return client.get(f"/api/v1/auth/google/callback?code=c&state={q['state'][0]}", follow_redirects=False)


def test_start_redirects_to_google_with_pkce_and_minimal_scope(client: TestClient) -> None:
    r = client.get("/api/v1/auth/google/start", follow_redirects=False)
    assert r.status_code == 303
    url = urlsplit(r.headers["location"])
    q = {k: v[0] for k, v in parse_qs(url.query).items()}
    assert f"{url.scheme}://{url.netloc}{url.path}" == "https://accounts.google.com/o/oauth2/v2/auth"
    assert q["scope"] == "openid"  # no email, no profile
    assert q["code_challenge_method"] == "S256" and q["client_id"] == CLIENT_ID
    assert q["redirect_uri"] == "http://localhost:8000/api/v1/auth/google/callback"
    flow = auth._unpack(client.cookies["lens_oauth"])
    assert flow is not None and flow["next"] == "/me"
    challenge = base64.urlsafe_b64encode(hashlib.sha256(flow["verifier"].encode()).digest()).rstrip(b"=").decode()
    assert q["code_challenge"] == challenge and q["state"] == flow["state"] and q["nonce"] == flow["nonce"]


def test_start_is_503_when_sign_in_is_not_configured(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(auth, "get_settings", lambda: Settings(_env_file=None))
    assert client.get("/api/v1/auth/google/start", follow_redirects=False).status_code == 503


def test_callback_signs_in_and_stores_only_a_hash(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, db: Session
) -> None:
    r = sign_in(client, monkeypatch, next="/for-you")
    assert r.status_code == 303 and r.headers["location"] == f"{WEB}/for-you"
    user = db.execute(select(User)).scalar_one()
    assert user.identity_provider == "google" and user.consent_at is not None
    assert user.identity_hash == hashlib.sha256(b"google:1234567890").hexdigest()
    state = client.get("/api/v1/me").json()
    assert state["consented"] and state["signed_in_with"] == "google" and state["sign_in_providers"] == ["google"]


@pytest.mark.parametrize(
    "bad",
    [
        {"iss": "https://evil.example"},
        {"aud": "someone-else.apps.googleusercontent.com"},
        {"exp": time.time() - 1},
        {"nonce": "replayed"},
        {"sub": ""},
    ],
)
def test_id_token_claims_are_checked(bad: dict[str, Any]) -> None:
    assert auth.valid_claims(claims(nonce="n"), "n")
    assert not auth.valid_claims({**claims(nonce="n"), **bad}, "n")


def test_state_mismatch_and_cancel_go_back_to_sign_in(client: TestClient, db: Session) -> None:
    client.get("/api/v1/auth/google/start", follow_redirects=False)
    r = client.get("/api/v1/auth/google/callback?code=c&state=forged", follow_redirects=False)
    assert r.headers["location"] == f"{WEB}/sign-in?error=state"
    r = client.get("/api/v1/auth/google/callback?error=access_denied", follow_redirects=False)
    assert r.headers["location"] == f"{WEB}/sign-in?error=cancelled"
    assert db.execute(select(User)).first() is None


@pytest.mark.parametrize("target", ["//evil.example/x", "https://evil.example", "/\\evil.example", None, "me"])
def test_next_never_leaves_the_site(target: str | None) -> None:
    assert auth.safe_next(target) == "/me"
    assert auth.safe_next("/story/abc?x=1") == "/story/abc?x=1"


def test_personalization_needs_sign_in(client: TestClient, db: Session) -> None:
    orphan = User(consent_at=datetime.now(UTC))  # a row without an identity (the old anonymous profile)
    db.add(orphan)
    db.flush()
    token = store.new_session(db, orphan)
    assert store.user_for_token(db, token) is None  # never a session
    client.cookies.set("lens_session", token)
    assert client.get("/api/v1/me").json()["consented"] is False
    assert client.get("/api/v1/me/feed").status_code == 401
    assert client.post("/api/v1/me/consent", headers=WRITE).status_code in (404, 405)


def test_signing_in_again_keeps_one_account_and_its_preferences(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, db: Session
) -> None:
    sign_in(client, monkeypatch)
    client.put("/api/v1/me/preferences", json={"key": "output_language", "value": "hi"}, headers=WRITE)
    client.cookies.clear()
    sign_in(client, monkeypatch)  # the same Google account on another browser
    assert len(db.execute(select(User)).scalars().all()) == 1
    assert client.get("/api/v1/me").json()["preferences"]["output_language"] == "hi"


def test_each_browser_has_its_own_session_and_sign_out_ends_only_this_one(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, db: Session
) -> None:
    sign_in(client, monkeypatch)
    laptop = client.cookies["lens_session"]
    client.cookies.clear()
    sign_in(client, monkeypatch)  # the phone
    assert len(db.execute(select(UserSession)).scalars().all()) == 2
    assert client.post("/api/v1/auth/sign-out").status_code == 403  # CSRF header required
    assert client.post("/api/v1/auth/sign-out", headers=WRITE).status_code == 204
    assert store.user_for_token(db, laptop) is not None  # the laptop is still signed in
    assert len(db.execute(select(UserSession)).scalars().all()) == 1
