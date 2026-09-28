"""Kill switch (G-OPS-03, ADR-0045): stop live generation per story, per topic, or everywhere.

- Story: `stories.kill_switch` takes the story down: hidden from every public page, never analysed, and its
  articles are never Ask evidence.
- Topic: no live generation for stories in these topics. Ask serves the stored, already-verified story
  summary instead (docs/07: serve precomputed only); analysis skips them.
- Global: no live generation anywhere. Ask says it can't answer right now; analysis pauses. Story pages
  keep serving their stored verified summaries.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from lens.db.models import OpsFlag, Story, StoryArticle

KEY = "generation"


@dataclass(frozen=True)
class Generation:
    off: bool = False
    off_topics: frozenset[str] = field(default_factory=frozenset)


def generation(session: Session) -> Generation:
    v: dict[str, Any] = session.execute(select(OpsFlag.value).where(OpsFlag.key == KEY)).scalar_one_or_none() or {}
    return Generation(bool(v.get("off", False)), frozenset(v.get("off_topics", [])))


def set_generation(session: Session, off: bool, off_topics: list[str]) -> Generation:
    value = {"off": off, "off_topics": sorted(set(off_topics))}
    stmt = insert(OpsFlag).values(key=KEY, value=value, updated_at=datetime.now(UTC))
    session.execute(
        stmt.on_conflict_do_update(
            index_elements=["key"], set_={"value": value, "updated_at": stmt.excluded.updated_at}
        )
    )
    return generation(session)


def generation_allowed(session: Session, story_ids: list[str]) -> bool:
    """False when generation is off globally or for the topic of any of these stories."""
    g = generation(session)
    if g.off:
        return False
    if not g.off_topics or not story_ids:
        return True
    ids = [uuid.UUID(i) for i in story_ids]
    topics = session.execute(select(Story.topic).where(Story.id.in_(ids))).scalars()
    return not any(t in g.off_topics for t in topics)


def set_story_killed(session: Session, story_id: uuid.UUID, killed: bool) -> bool:
    story = session.get(Story, story_id)
    if story is None:
        return False
    story.kill_switch = killed
    return True


def taken_down_articles(article_ids: list[uuid.UUID]) -> Any:
    """SQL for the articles among these that belong to a taken-down story (never Ask evidence)."""
    return (
        select(StoryArticle.article_id)
        .join(Story, Story.id == StoryArticle.story_id)
        .where(Story.kill_switch, StoryArticle.article_id.in_(article_ids))
    )
