"""Sign-in (ADR-0044): OpenID Connect authorization code flow with PKCE, run by the API.

GET  /auth/google/start?next=/me   -> redirect to Google, with state, nonce and a PKCE challenge
GET  /auth/google/callback          -> code for tokens (server to server), then the session cookie
POST /auth/sign-out                 -> ends this browser's session (X-Lens-Client, like /me writes)

The ID token comes straight from Google's token endpoint over TLS in exchange for our client secret, so
its claims are checked (issuer, audience, expiry, nonce) without a signature check (OIDC Core 3.1.3.7).
Scope is `openid` only: no email, no name. Errors return to the web app's /sign-in?error=<code>.
"""

from __future__ import annotations

import base64
import hashlib
import json
import secrets
import time
from typing import Annotated, Any
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Cookie, Depends, HTTPException, Response
from fastapi.responses import RedirectResponse

from lens.api.limits import limit
from lens.api.routers.me import CSRF, DB, Token, set_session_cookie
from lens.core.config_files import load_yaml
from lens.core.logging import get_logger
from lens.core.settings import get_settings
from lens.memory import store

router = APIRouter(prefix="/auth", tags=["auth"], dependencies=[Depends(limit("me"))])
log = get_logger(__name__)
PROVIDER = "google"


def _cfg() -> dict[str, Any]:
    return load_yaml("auth.yaml")


FLOW = _cfg()["flow_cookie"]
FLOW_PATH = "/api/v1/auth"


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def _pack(state: str, nonce: str, verifier: str, next_path: str) -> str:
    """Flow cookie value: cookie-safe (token_urlsafe parts, `next` base64url), no quoting needed."""
    return ".".join([state, nonce, verifier, _b64(next_path.encode())])


def _unpack(raw: str | None) -> dict[str, str] | None:
    parts = (raw or "").split(".")
    if len(parts) != 4:
        return None
    try:
        next_path = base64.urlsafe_b64decode(parts[3] + "=" * (-len(parts[3]) % 4)).decode()
    except ValueError:
        return None
    return {"state": parts[0], "nonce": parts[1], "verifier": parts[2], "next": next_path}


def _redirect_uri() -> str:
    return f"{get_settings().api_public_url.rstrip('/')}/api/v1/auth/{PROVIDER}/callback"


def safe_next(path: str | None) -> str:
    """Only a path on the web app, never another site (open redirect)."""
    if path and path.startswith("/") and not path.startswith("//") and "\\" not in path and len(path) <= 200:
        return path
    return "/me"


def _back(path: str) -> RedirectResponse:
    r = RedirectResponse(f"{get_settings().web_origin.rstrip('/')}{path}", status_code=303)
    r.delete_cookie(FLOW, path=FLOW_PATH)
    return r


def _fail(code: str) -> RedirectResponse:
    return _back(f"/sign-in?error={code}")


@router.get(f"/{PROVIDER}/start")
def start(next: str | None = None) -> RedirectResponse:
    s = get_settings()
    if not s.google_client_id:
        raise HTTPException(503, "sign-in is not configured")
    p = _cfg()["providers"][PROVIDER]
    state, nonce, verifier = secrets.token_urlsafe(24), secrets.token_urlsafe(24), secrets.token_urlsafe(48)
    query = {
        "client_id": s.google_client_id,
        "redirect_uri": _redirect_uri(),
        "response_type": "code",
        "scope": p["scope"],
        "state": state,
        "nonce": nonce,
        "code_challenge": _b64(hashlib.sha256(verifier.encode()).digest()),
        "code_challenge_method": "S256",
        "prompt": "select_account",
    }
    r = RedirectResponse(f"{p['authorization_endpoint']}?{urlencode(query)}", status_code=303)
    r.set_cookie(
        FLOW,
        _pack(state, nonce, verifier, safe_next(next)),
        max_age=_cfg()["flow_max_age_s"],
        httponly=True,
        samesite="lax",  # sent on Google's top-level redirect back to us
        secure=s.app_env != "dev",
        path=FLOW_PATH,
    )
    return r


def exchange(code: str, verifier: str) -> dict[str, Any]:
    """Code for tokens at the provider (server to server); returns the ID token's claims."""
    s = get_settings()
    if not (s.google_client_id and s.google_client_secret):
        raise ValueError("sign-in is not configured")
    res = httpx.post(
        _cfg()["providers"][PROVIDER]["token_endpoint"],
        data={
            "code": code,
            "client_id": s.google_client_id,
            "client_secret": s.google_client_secret.get_secret_value(),
            "redirect_uri": _redirect_uri(),
            "grant_type": "authorization_code",
            "code_verifier": verifier,
        },
        timeout=10,
    )
    res.raise_for_status()
    payload = res.json()["id_token"].split(".")[1]
    claims: dict[str, Any] = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
    return claims


def valid_claims(claims: dict[str, Any], nonce: str, now: float | None = None) -> bool:
    client_id = get_settings().google_client_id
    aud = claims.get("aud")
    return (
        claims.get("iss") in _cfg()["providers"][PROVIDER]["issuers"]
        and (aud == client_id or (isinstance(aud, list) and client_id in aud))
        and float(claims.get("exp", 0)) > (now if now is not None else time.time())
        and secrets.compare_digest(str(claims.get("nonce", "")), nonce)
        and bool(claims.get("sub"))
    )


@router.get(f"/{PROVIDER}/callback")
def callback(
    db: DB,
    token: Token = None,
    flow: Annotated[str | None, Cookie(alias=FLOW)] = None,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
) -> RedirectResponse:
    if error:
        return _fail("cancelled" if error == "access_denied" else "provider")
    f = _unpack(flow)
    if f is None:
        return _fail("expired")
    if not code or not state or not secrets.compare_digest(state, f["state"]):
        return _fail("state")
    try:
        claims = exchange(code, f["verifier"])
    except (httpx.HTTPError, KeyError, ValueError, IndexError) as e:
        log.warning("auth.exchange_failed", provider=PROVIDER, error=type(e).__name__)
        return _fail("provider")
    if not valid_claims(claims, f["nonce"]):
        log.warning("auth.bad_id_token", provider=PROVIDER)
        return _fail("provider")
    account = store.sign_in(db, PROVIDER, str(claims["sub"]))
    r = _back(safe_next(f["next"]))
    store.end_session(db, token)  # a fresh session per sign-in; any earlier one on this browser ends
    set_session_cookie(r, store.new_session(db, account))
    db.commit()
    log.info("auth.signed_in", provider=PROVIDER)
    return r


@router.post("/sign-out", status_code=204, dependencies=[CSRF])
def sign_out(db: DB, response: Response, token: Token = None) -> None:
    store.end_session(db, token)
    db.commit()
    response.delete_cookie(store.cfg()["cookie"]["name"], path="/api/v1")
