"""Kill switch (G-OPS-03, ADR-0045): per story, per topic and global, end to end."""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.orm import Session

from lens.api import limits
from lens.core.settings import get_settings
from lens.db.models import StoryArticle
from lens.ops import kill
from lens.schemas.analysis import FaithfulnessVerdict
from lens.schemas.ask import AskDraft, QueryUnderstanding
from tests.test_api_public import _src, _story
from tests.test_ask_graph import PASS, ST1, FakeRetriever, _draft, _ev, _qu, _run
from tests.test_security import Counter
from tests.test_story_graph import FakeLLM

ADMIN = {"authorization": "Bearer " + "k" * 40}


@pytest.fixture
def admin(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "admin_token", SecretStr("k" * 40))
    monkeypatch.setattr(limits, "_redis", lambda: Counter())  # the admin limit is covered in test_security


def test_story_kill_takes_it_down_and_restore_brings_it_back(client: Any, db: Session, admin: None) -> None:
    story = _story(db, [_src(db, f"o{i}") for i in range(4)])
    assert client.get(f"/api/v1/stories/{story.id}").status_code == 200
    assert client.post(f"/api/v1/admin/stories/{story.id}/kill").status_code == 401  # admin only
    assert client.post(f"/api/v1/admin/stories/{story.id}/kill", headers=ADMIN).json()["killed"] is True
    assert client.get(f"/api/v1/stories/{story.id}").status_code == 404
    assert story.slug not in [s["slug"] for s in client.get("/api/v1/feed").json()["items"]]
    assert client.post(f"/api/v1/admin/stories/{story.id}/restore", headers=ADMIN).json()["killed"] is False
    assert client.get(f"/api/v1/stories/{story.id}").status_code == 200
    missing = "00000000-0000-0000-0000-000000000000"
    assert client.post(f"/api/v1/admin/stories/{missing}/kill", headers=ADMIN).status_code == 404


def test_taken_down_story_articles_are_never_ask_evidence(db: Session) -> None:
    story = _story(db, [_src(db, "a1"), _src(db, "a2")])
    ids = list(db.execute(select(StoryArticle.article_id).where(StoryArticle.story_id == story.id)).scalars())
    assert ids and list(db.execute(kill.taken_down_articles(ids)).scalars()) == []
    story.kill_switch = True
    db.flush()
    assert set(db.execute(kill.taken_down_articles(ids)).scalars()) == set(ids)


def test_generation_switch_api_validates_topics(client: Any, db: Session, admin: None) -> None:
    assert client.get("/api/v1/admin/kill-switch", headers=ADMIN).json() == {"off": False, "off_topics": []}
    r = client.post("/api/v1/admin/kill-switch", json={"off_topics": ["bjp"]}, headers=ADMIN)
    assert r.status_code == 422 and r.json()["error"]["code"] == "unknown_topic"
    r = client.post("/api/v1/admin/kill-switch", json={"off": False, "off_topics": ["politics"]}, headers=ADMIN)
    assert r.json() == {"off": False, "off_topics": ["politics"]}
    assert client.get("/api/v1/admin/kill-switch", headers=ADMIN).json()["off_topics"] == ["politics"]


def test_generation_allowed_by_topic_and_globally(db: Session) -> None:
    politics, sports = _story(db, [_src(db, "p")]), _story(db, [_src(db, "s")])
    politics.topic, sports.topic = "politics", "sports"
    db.flush()
    assert kill.generation_allowed(db, [str(politics.id)])
    kill.set_generation(db, False, ["politics"])
    assert not kill.generation_allowed(db, [str(politics.id), str(sports.id)])
    assert kill.generation_allowed(db, [str(sports.id)])
    kill.set_generation(db, True, [])
    assert not kill.generation_allowed(db, [str(sports.id)])


def test_topic_switch_serves_the_stored_summary_without_writing() -> None:
    script: dict[type, list[Any]] = {QueryUnderstanding: [_qu()], AskDraft: [_draft()], FaithfulnessVerdict: [PASS]}
    stored = {"story_id": ST1, "detail": "stored"}
    out, llm, _ = _run(script, stored=stored, generation_allowed=lambda ids: False)
    assert out["outcome"] == "fallback" and out["fallback"] == stored
    assert AskDraft not in llm.kwargs  # nothing was generated
    out, _, _ = _run(script, stored=None, generation_allowed=lambda ids: False)
    assert out["outcome"] == "abstain"  # no stored summary: abstain, never a live answer


def test_global_switch_answers_nothing_live(db: Session) -> None:
    kill.set_generation(db, True, [])
    llm = FakeLLM({QueryUnderstanding: [_qu()], AskDraft: [_draft()], FaithfulnessVerdict: [PASS]})
    from lens.agents.online.ask_graph import build
    from lens.services.ask import ask_events

    events = list(ask_events(db, "q", build(llm, FakeRetriever(_ev()), lambda ids: None)))
    kind, final = events[-1]
    assert kind == "abstain" and getattr(final, "reason", None) == "service_unavailable"
    assert llm.kwargs == {}  # no model was called at all
