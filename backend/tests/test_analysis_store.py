"""Story analysis storage and serving against Postgres (fake LLM): claims with verified offsets,
versioned summaries, guard events, review routing, retry of failures, and the API view."""

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from lens.agents.offline.evidence import select_evidence
from lens.agents.offline.story_graph import build
from lens.db.models import Claim, GuardEvent, ReviewQueueItem, Source, Story, StorySummary
from lens.pipeline.analyze import eligible, load_articles, store
from lens.schemas.analysis import CitedSentence, ClaimList, FaithfulnessVerdict, StoryFraming, SummaryDraft
from tests.test_api_public import _src, _story
from tests.test_story_graph import FakeLLM

pytestmark = pytest.mark.db


def _cs(text: str, *refs: str) -> CitedSentence:
    return CitedSentence(text=text, citations=list(refs))


def _script(quote: str) -> dict[type, list[Any]]:
    from lens.schemas.analysis import Claim as ClaimOut

    return {
        ClaimList: [
            ClaimList(
                claims=[ClaimOut(article_ref="A1", text="c", source_quote=quote, attributed_to=None, checkable=True)]
            )
        ],
        StoryFraming: [
            StoryFraming(
                rationale="r",
                framing_differences=[_cs("A1 leads with X.", "A1")],
                only_in_some_coverage=[_cs("Only A2 names Y.", "A2")],
            )
        ],
        SummaryDraft: [
            SummaryDraft(summary=[_cs("First.", "A1", "A2"), _cs("Second.", "A2")], agreements=[], disagreements=[])
        ],
        FaithfulnessVerdict: [FaithfulnessVerdict(reasoning="ok", unsupported_sentences=[], verdict="pass")],
    }


def _analyze(db: Session, story: Story, headline: str | None = None) -> StorySummary:
    ev = select_evidence(load_articles(db, story), 12)
    state = build(FakeLLM(_script(ev[0].text.split("\n")[0][:12]))).invoke(
        {
            "story_id": str(story.id),
            "headline": headline or story.headline,
            "evidence": ev,
            "sensitive_keywords": {"terror_incident": ["bombing"]},
        }
    )
    return store(db, story, state)


@pytest.fixture
def four(db: Session) -> Story:
    srcs: list[Source] = [_src(db, f"an-{i}", "en" if i % 2 else "hi") for i in range(4)]
    return _story(db, srcs, slug="analysed-story")


def test_store_writes_claims_summary_and_guard_events(db: Session, four: Story) -> None:
    row = _analyze(db, four)
    assert row.state == "published" and row.version == 1 and row.source_count == 4
    assert [s["text"] for s in row.summary] == ["First.", "Second."]
    assert row.summary[0]["citations"][0]["source_name"].startswith("AN-")  # names re-attached in code
    claim = db.execute(select(Claim)).scalar_one()
    assert claim.char_end > claim.char_start and claim.prompt_version and claim.schema_version == "1.0"
    guards = {g for (g,) in db.execute(select(GuardEvent.guard_id))}
    assert guards == {"G-GEN-01", "G-GEN-02", "G-GEN-03", "G-OUT-07"}
    assert _analyze(db, four).version == 2  # versioned, never overwritten


def test_sensitive_story_is_queued_and_not_served(db: Session, four: Story, client: TestClient) -> None:
    row = _analyze(db, four, headline="Court convicts accused in bombing case")
    assert row.state == "review"
    assert db.execute(select(ReviewQueueItem.ref_id)).scalar_one() == row.id
    assert client.get("/api/v1/stories/analysed-story").json()["summary"] is None


def test_api_serves_latest_published_summary_with_numbered_citations(
    db: Session, four: Story, client: TestClient
) -> None:
    _analyze(db, four)
    body = client.get("/api/v1/stories/analysed-story").json()
    s = body["summary"]
    assert s["verified"] is True and s["version"] == 1
    assert [c["n"] for sent in s["sentences"] for c in sent["citations"]] == [1, 2, 3]
    # Masked refs in the text become the cited outlets' names (re-attached in code).
    diffs = body["framing_differences"]
    assert diffs[0]["text"] == f"{diffs[0]['citations'][0]['source_name']} leads with X."
    assert diffs[1]["text"] == f"Only {diffs[1]['citations'][0]['source_name']} names Y."
    assert body["framing_differences"][0]["citations"][0]["n"] == 4  # numbering continues after the summary
    card = next(c for c in client.get("/api/v1/feed").json()["items"] if c["slug"] == "analysed-story")
    assert card["summary_preview"] == "First."


def test_eligibility_skips_analysed_and_retries_old_failures(db: Session, four: Story) -> None:
    assert four.id in {s.id for s in eligible(db, 50)}
    row = _analyze(db, four)
    assert four.id not in {s.id for s in eligible(db, 50)}
    row.state, row.created_at = "failed", datetime.now(UTC) - timedelta(hours=7)
    db.flush()
    assert four.id in {s.id for s in eligible(db, 50)}  # failure older than reanalysis_trigger.hours
    assert db.execute(select(func.count()).select_from(StorySummary)).scalar_one() == 1


def test_review_queue_approve_publishes_the_held_version(
    db: Session, four: Story, client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from pydantic import SecretStr

    from lens.core.settings import get_settings

    monkeypatch.setattr(get_settings(), "admin_token", SecretStr("t"))
    auth = {"authorization": "Bearer t"}
    _analyze(db, four, headline="Court convicts accused in bombing case")
    items = client.get("/api/v1/admin/review-queue", headers=auth).json()["items"]
    assert len(items) == 1 and "terror_incident" in items[0]["reason"] and items[0]["summary"] == ["First.", "Second."]
    assert client.get("/api/v1/stories/analysed-story").json()["summary"] is None
    r = client.post(
        f"/api/v1/admin/review-queue/{items[0]['id']}/resolve", params={"decision": "approve"}, headers=auth
    )
    assert r.json() == {"status": "approved"}
    assert client.get("/api/v1/stories/analysed-story").json()["summary"]["version"] == 1
    again = client.post(
        f"/api/v1/admin/review-queue/{items[0]['id']}/resolve", params={"decision": "approve"}, headers=auth
    )
    assert again.status_code == 404
    assert client.get("/api/v1/admin/review-queue").status_code == 401


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (
            "Some coverage leads with the score (A1, A2), while other coverage does not (A2).",
            "Some coverage leads with the score, while other coverage does not.",
        ),
        ("According to A2, police made arrests.", "According to AN-2, police made arrests."),
        ("A1 and A2 agree on the date.", "AN-1 and AN-2 agree on the date."),
        ("A total of A12 things (Asian Games 2026).", "A total of A12 things (Asian Games 2026)."),  # unknown ref kept
    ],
)
def test_masked_refs_become_outlet_names(text: str, expected: str) -> None:
    from lens.services.stories import _unmask

    assert _unmask(text, {"A1": "AN-1", "A2": "AN-2"}) == expected
