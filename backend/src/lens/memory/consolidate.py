"""Memory consolidation (docs/11): a cheap model reads a consented reader's recent questions and proposes
explicit preferences as `UserFact`s. Every proposal is validated against the closed keys and values
(`store.validate`); anything else is discarded and logged. It never summarizes what news someone read.

Trigger: `consolidation.after_sessions` new Ask sessions since the last run, or nightly.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from langsmith import traceable
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from lens.agents.offline.evidence import clean
from lens.agents.prompts import skill
from lens.core.logging import get_logger
from lens.db.models import AskTurn, User
from lens.memory import store
from lens.schemas.memory import ConsolidatedFacts

log = get_logger(__name__)
LLM = Callable[..., Any]


def due_users(session: Session, now: datetime) -> list[User]:
    """Consented users with enough new sessions since their last run, or new turns and a run over a day ago."""
    c = store.cfg()["consolidation"]
    out = []
    for user in session.execute(select(User).where(User.consent_at.is_not(None))).scalars():
        since = user.consolidated_at or user.consent_at
        new = session.execute(
            select(func.count(func.distinct(AskTurn.session_id)), func.count()).where(
                AskTurn.user_id == user.id, AskTurn.created_at > since
            )
        ).one()
        nightly = user.consolidated_at is None or now - user.consolidated_at >= timedelta(days=1)
        if new[0] >= c["after_sessions"] or (new[1] and nightly):
            out.append(user)
    return out


@traceable(name="memory.consolidate", run_type="chain", tags=["memory"])
def consolidate_user(session: Session, user: User, llm: LLM, now: datetime | None = None) -> dict[str, Any]:
    now = now or datetime.now(UTC)
    c = store.cfg()["consolidation"]
    since = user.consolidated_at or user.consent_at
    questions = (
        session.execute(
            select(AskTurn.raw_query)  # PII-masked at storage (G-OUT-05)
            .where(AskTurn.user_id == user.id, AskTurn.created_at > since)
            .order_by(AskTurn.created_at.desc())
            .limit(c["max_turns"])
        )
        .scalars()
        .all()
    )
    stats: dict[str, Any] = {"questions": len(questions), "stored": [], "rejected": 0}
    if questions:
        s = skill("memory_consolidation")
        body = "\n".join(f"- {clean(q)}" for q in questions)
        out: ConsolidatedFacts = llm(
            "triage",
            ConsolidatedFacts,
            s.text,
            f"<questions>\n{body}\n</questions>",
            run_name="memory.consolidation",
            prompt_version=f"memory_consolidation@{s.version}",
        )
        for fact in out.facts:
            try:
                stored = store.set_fact(session, user, fact.key.value, fact.value, now)
                stats["stored"].append(stored.key.value)
            except store.MemoryRejected:  # logged by the store (memory.rejected)
                stats["rejected"] += 1
    user.consolidated_at = now
    session.flush()
    return stats


def run(session: Session, llm: LLM, now: datetime | None = None) -> dict[str, int]:
    now = now or datetime.now(UTC)
    users = due_users(session, now)
    stored = rejected = 0
    for u in users:
        r = consolidate_user(session, u, llm, now)
        stored, rejected = stored + len(r["stored"]), rejected + r["rejected"]
    return {"users": len(users), "stored": stored, "rejected": rejected}
