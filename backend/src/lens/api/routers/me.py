"""/me: the reader's own memory (docs/09, docs/11, ADR-0041). Anonymous, consented profile in an httpOnly cookie.
Mutating calls need the `X-Lens-Client` header: a cross-site page cannot send it with credentials (CSRF)."""

from __future__ import annotations

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Cookie, Depends, Header, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from lens.api.limits import limit
from lens.core.settings import get_settings
from lens.db.models import AskTurn, Story, StoryView, User
from lens.db.session import get_session
from lens.memory import store
from lens.memory.changes import changes_since_last_view
from lens.schemas import api
from lens.services import stories as stories_svc

router = APIRouter(prefix="/me", tags=["me"], dependencies=[Depends(limit("me"))])
DB = Annotated[Session, Depends(get_session)]
COOKIE = store.cfg()["cookie"]["name"]
Token = Annotated[str | None, Cookie(alias=COOKIE)]


def _csrf(x_lens_client: Annotated[str | None, Header()] = None) -> None:
    if not x_lens_client:
        raise HTTPException(403, "missing X-Lens-Client header")


CSRF = Depends(_csrf)


def _user(db: Session, token: str | None) -> User:
    user = store.user_for_token(db, token)
    if user is None or user.consent_at is None:
        raise HTTPException(401, "memory is off: consent first (POST /me/consent)")
    return user


def _set_cookie(response: Response, token: str) -> None:
    c = store.cfg()["cookie"]
    response.set_cookie(
        c["name"],
        token,
        max_age=c["max_age_days"] * 86400,
        httponly=True,
        samesite="lax",
        secure=get_settings().app_env != "dev",
        path="/api/v1",
    )


def _allowed() -> dict[str, list[str]]:
    return {k: [str(v) for v in vals] for k, vals in store.cfg()["values"].items()}


@router.get("", response_model=api.MeState)
def me(db: DB, response: Response, token: Token = None) -> api.MeState:
    response.headers["Cache-Control"] = "no-store"
    user = store.user_for_token(db, token)
    return api.MeState(consented=user is not None, preferences=store.preferences(db, user), allowed=_allowed())


@router.post("/consent", response_model=api.MeState, dependencies=[CSRF])
def give_consent(db: DB, response: Response, token: Token = None) -> api.MeState:
    user = store.user_for_token(db, token)
    if user is None:
        user, raw = store.consent(db)
        db.commit()
        _set_cookie(response, raw)
    return api.MeState(consented=True, preferences=store.preferences(db, user), allowed=_allowed())


@router.put("/preferences", response_model=api.MeState, dependencies=[CSRF])
def put_preference(body: api.PreferenceUpdate, db: DB, token: Token = None) -> api.MeState:
    user = store.user_for_token(db, token)
    try:
        store.set_fact(db, user, body.key, body.value)
    except store.MemoryRejected as e:
        raise HTTPException(401 if user is None else 422, str(e)) from None
    db.commit()
    return api.MeState(consented=True, preferences=store.preferences(db, user), allowed=_allowed())


@router.get("/memory", response_model=api.MemoryView)
def memory(db: DB, response: Response, token: Token = None) -> api.MemoryView:
    response.headers["Cache-Control"] = "no-store"
    user = _user(db, token)
    views = db.execute(
        select(StoryView, Story.headline)
        .join(Story, Story.id == StoryView.story_id)
        .where(StoryView.user_id == user.id)
        .order_by(StoryView.viewed_at.desc())
    ).all()
    asks = db.execute(select(AskTurn).where(AskTurn.user_id == user.id).order_by(AskTurn.created_at.desc())).scalars()
    return api.MemoryView(
        preferences=store.preferences(db, user),
        story_views=[
            api.MemoryStoryView(id=str(v.id), story_id=str(v.story_id), headline=h, viewed_at=v.viewed_at)
            for v, h in views
        ],
        ask_history=[api.MemoryAsk(id=str(t.id), question=t.raw_query, created_at=t.created_at) for t in asks],
        retention_days=store.cfg()["retention_days"],
    )


@router.delete("/memory", status_code=204, dependencies=[CSRF])
def delete_everything(db: DB, response: Response, token: Token = None) -> None:
    store.delete_everything(db, _user(db, token))
    db.commit()
    response.delete_cookie(COOKIE, path="/api/v1")


@router.delete("/memory/preferences/{key}", status_code=204, dependencies=[CSRF])
def delete_preference(key: str, db: DB, token: Token = None) -> None:
    store.delete_fact(db, _user(db, token), key)
    db.commit()


@router.delete("/memory/views/{view_id}", status_code=204, dependencies=[CSRF])
def delete_view(view_id: uuid.UUID, db: DB, token: Token = None) -> None:
    store.delete_view(db, _user(db, token), view_id)
    db.commit()


@router.delete("/memory/asks/{turn_id}", status_code=204, dependencies=[CSRF])
def delete_ask(turn_id: uuid.UUID, db: DB, token: Token = None) -> None:
    store.unlink_ask(db, _user(db, token), turn_id)
    db.commit()


@router.post("/views/{story_id}", response_model=api.StoryChanges | None, dependencies=[CSRF])
def view_story(story_id: uuid.UUID, db: DB, token: Token = None) -> Any:
    """Records a view and returns what changed since the previous one (null on a first visit)."""
    user = _user(db, token)
    changes = changes_since_last_view(db, user, story_id)
    store.record_view(db, user, story_id)
    db.commit()
    return changes


@router.get("/feed", response_model=api.StoryCardPage)
def for_you(db: DB, response: Response, token: Token = None, cursor: str | None = None) -> api.StoryCardPage:
    """For you: stories in the reader's followed topics. Ordering and selection only; outlets never change."""
    response.headers["Cache-Control"] = "private, no-store"
    user = _user(db, token)
    topics = store.preferences(db, user).get("followed_topics") or []
    return stories_svc.feed(db, topics=list(topics), cursor=cursor)
