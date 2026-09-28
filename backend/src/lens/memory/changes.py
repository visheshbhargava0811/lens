"""Episodic memory feature (docs/11): "What changed since you last looked". Deterministic: the reader's
previous view of a story, then the articles and fact-checks published after it."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from lens.db.models import Article, Source, StoryArticle, StorySummary, StoryView, User
from lens.schemas import api
from lens.services.stories import story_fact_checks


def changes_since_last_view(session: Session, user: User, story_id: uuid.UUID) -> api.StoryChanges | None:
    last = session.execute(
        select(StoryView)
        .where(StoryView.user_id == user.id, StoryView.story_id == story_id)
        .order_by(StoryView.viewed_at.desc())
        .limit(1)
    ).scalar_one_or_none()
    if last is None:
        return None
    rows = session.execute(
        select(Article, Source)
        .join(StoryArticle, StoryArticle.article_id == Article.id)
        .join(Source, Source.id == Article.source_id)
        .where(StoryArticle.story_id == story_id, Article.published_at > last.viewed_at)
        .order_by(Article.published_at.desc())
        .limit(20)
    ).all()
    current = session.execute(
        select(StorySummary.version)
        .where(StorySummary.story_id == story_id, StorySummary.state == "published")
        .order_by(StorySummary.version.desc())
        .limit(1)
    ).scalar_one_or_none()
    checks = [
        f
        for f in story_fact_checks(session, [story_id], limit=20)
        if f.published_at is not None and f.published_at > last.viewed_at
    ]
    return api.StoryChanges(
        since=last.viewed_at,
        new_articles=[
            api.AskArticle(
                id=str(a.id),
                headline=a.title,
                headline_lang=a.language,
                url=a.canonical_url or a.url,
                source_name=src.name,
                source_language=a.language,
            )
            for a, src in rows
        ],
        new_fact_checks=checks,
        summary_updated=current is not None and (last.story_version_seen or 0) < current,
    )
