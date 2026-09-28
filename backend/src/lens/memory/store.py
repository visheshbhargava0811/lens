"""User memory (docs/11, ADR-0041): an anonymous, consented profile holding explicit preferences, story views
and Ask history. Consent first, closed keys and values, real deletion, retention purge.

Identity: consenting creates a `users` row and a random session token; the browser keeps the token in an
httpOnly cookie and the database keeps only its SHA-256. No email, no name, nothing else identifying.
"""

from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from lens.core.config_files import load_yaml
from lens.core.logging import get_logger
from lens.db.models import AskTurn, StorySummary, StoryView, User, UserPreference
from lens.schemas.memory import UserFact, UserFactKey

log = get_logger(__name__)
LIST_KEYS = {UserFactKey.followed_topics, UserFactKey.followed_regions}


class MemoryRejected(ValueError):
    """A write that memory must refuse: no consent, a key outside the enum, or a value outside its set."""


def cfg() -> dict[str, Any]:
    c: dict[str, Any] = load_yaml("memory.yaml")
    return c


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def consent(session: Session, now: datetime | None = None) -> tuple[User, str]:
    """Creates a consented profile; returns it and the raw token for the cookie (never stored)."""
    token = secrets.token_urlsafe(32)
    user = User(consent_at=now or datetime.now(UTC), session_token_hash=_hash(token))
    session.add(user)
    session.flush()
    return user, token


def user_for_token(session: Session, token: str | None) -> User | None:
    if not token:
        return None
    return session.execute(select(User).where(User.session_token_hash == _hash(token))).scalar_one_or_none()


def validate(key: str, value: Any) -> UserFact:
    """Closed keys and closed values; everything else raises MemoryRejected and is logged."""
    try:
        k = UserFactKey(key)
    except ValueError:
        log.warning("memory.rejected", reason="key_not_in_enum", key=str(key)[:40])
        raise MemoryRejected(f"not a storable preference: {key!r}") from None
    allowed = set(cfg()["values"][k.value])
    values = value if isinstance(value, list) else [value]
    if (k in LIST_KEYS) != isinstance(value, list) or not all(isinstance(v, str) for v in values):
        log.warning("memory.rejected", reason="wrong_shape", key=k.value)
        raise MemoryRejected(f"{k.value} takes {'a list' if k in LIST_KEYS else 'one value'}")
    bad = [v for v in values if v not in allowed]
    if bad or len(values) > cfg()["max_list_items"]:
        log.warning("memory.rejected", reason="value_not_allowed", key=k.value, count=len(bad))
        raise MemoryRejected(f"{k.value}: value not allowed")
    return UserFact(key=k, value=sorted(set(values)) if k in LIST_KEYS else values[0])


def set_fact(session: Session, user: User | None, key: str, value: Any, now: datetime | None = None) -> UserFact:
    if user is None or user.consent_at is None:
        log.warning("memory.rejected", reason="no_consent", key=str(key)[:40])
        raise MemoryRejected("no consent: memory is off")  # docs/11 hard rule 5
    fact = validate(key, value)
    row = session.get(UserPreference, (user.id, fact.key.value))
    if row is None:
        session.add(UserPreference(user_id=user.id, key=fact.key.value, value=fact.value))
    else:
        row.value, row.updated_at = fact.value, now or datetime.now(UTC)
    session.flush()
    return fact


def preferences(session: Session, user: User | None) -> dict[str, Any]:
    if user is None:
        return {}
    return {
        p.key: p.value
        for p in session.execute(select(UserPreference).where(UserPreference.user_id == user.id)).scalars()
    }


def delete_fact(session: Session, user: User, key: str) -> None:
    session.execute(delete(UserPreference).where(UserPreference.user_id == user.id, UserPreference.key == key))


def delete_view(session: Session, user: User, view_id: uuid.UUID) -> None:
    session.execute(delete(StoryView).where(StoryView.id == view_id, StoryView.user_id == user.id))


def unlink_ask(session: Session, user: User, turn_id: uuid.UUID) -> None:
    """The audit row (G-OPS-04) stays anonymous until its own purge; it is no longer the reader's history."""
    session.execute(update(AskTurn).where(AskTurn.id == turn_id, AskTurn.user_id == user.id).values(user_id=None))


def delete_everything(session: Session, user: User) -> None:
    """docs/11 hard rule 6: the user row goes; preferences and story views cascade, Ask turns are unlinked."""
    session.execute(update(AskTurn).where(AskTurn.user_id == user.id).values(user_id=None))
    session.execute(delete(User).where(User.id == user.id))
    session.flush()


def record_view(
    session: Session, user: User | None, story_id: uuid.UUID, now: datetime | None = None
) -> StoryView | None:
    """Episodic memory: only for consented users. Stores which summary version was on screen."""
    if user is None or user.consent_at is None:
        return None
    version = session.execute(
        select(StorySummary.version)
        .where(StorySummary.story_id == story_id, StorySummary.state == "published")
        .order_by(StorySummary.version.desc())
        .limit(1)
    ).scalar_one_or_none()
    view = StoryView(user_id=user.id, story_id=story_id, viewed_at=now or datetime.now(UTC), story_version_seen=version)
    session.add(view)
    session.flush()
    return view


def purge(session: Session, now: datetime | None = None) -> int:
    """docs/11 hard rule 7: story views older than `retention_days` are deleted (Ask turns: G-OPS-04 purge)."""
    cutoff = (now or datetime.now(UTC)) - timedelta(days=cfg()["retention_days"])
    result: Any = session.execute(delete(StoryView).where(StoryView.viewed_at < cutoff))
    return int(result.rowcount)  # DELETE returns a CursorResult
