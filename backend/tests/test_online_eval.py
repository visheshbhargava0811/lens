"""docs/08 online evaluators on sampled Ask turns."""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from lens.db.models import Article, AskTurn, GuardEvent, Source
from lens.ingest.parse import RawItem
from lens.ingest.store import store_items
from lens.ops import online_eval
from lens.schemas.analysis import FaithfulnessVerdict

NOW = datetime(2026, 9, 27, 12, tzinfo=UTC)


@pytest.fixture(autouse=True)
def cfg(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        online_eval,
        "_cfg",
        lambda: {
            "sample_pct": 100,
            "judge_per_pass": 1,
            "lookback_hours": 24,
            "min_samples_for_alert": 2,
            "floors": {"citation_presence": 1.0, "premise_handled": 0.95, "faithfulness": 0.95},
        },
    )


def _article(db: Session) -> str:
    s = Source(slug="t", name="T", homepage_url="https://t.example", language_codes=["en"], region="national")
    db.add(s)
    db.flush()
    raw = RawItem("https://t.example/1", "RBI keeps repo rate unchanged", None, NOW, None, None)
    store_items(db, s, [raw], NOW)
    return str(db.execute(select(Article.id)).scalar_one())


def _turn(db: Session, q: str, outcome: str, sentences: list[dict[str, Any]] | None = None) -> AskTurn:
    t = AskTurn(
        session_id=uuid.uuid4(),
        raw_query=q,
        outcome=outcome,
        answer={"tldr": sentences or [], "limitations": []} if outcome != "abstain" else None,
        langsmith_run_id=str(uuid.uuid4()),
        created_at=NOW - timedelta(minutes=5),
    )
    db.add(t)
    db.flush()
    return t


def test_scores_feedback_and_alerts(db: Session) -> None:
    aid = _article(db)
    cited = [{"text": "The RBI kept the repo rate unchanged.", "citations": [{"article_id": aid}]}]
    _turn(db, "What did the RBI decide?", "answer", cited)
    _turn(db, "Why did the RBI cut rates?", "answer", [{"text": "Rates moved.", "citations": []}])
    calls: list[str] = []

    def llm(tier: str, model: type, system: str, user: str, **kw: Any) -> FaithfulnessVerdict:
        calls.append(user)
        return FaithfulnessVerdict(reasoning="r", unsupported_sentences=[], verdict="pass")

    fb: list[tuple[str, str, float]] = []
    out = online_eval.run(db, llm, NOW, feedback=lambda rid, key, score: fb.append((rid, key, score)))
    assert out["turns"] == 2 and out["sampled"] == 2 and out["judged"] == 1  # judge capped per pass
    assert "A1" in calls[0] and "RBI keeps repo rate unchanged" in calls[0]  # judged against the cited text
    keys = {(k, s) for _, k, s in fb}
    assert ("online.citation_presence", 1.0) in keys and ("online.citation_presence", 0.0) in keys
    assert ("online.premise_handled", 0.0) in keys  # "why did" question with no premise note
    assert {a["metric"] for a in out["alerts"]} == {"citation_presence"}  # mean 0.5 < 1.0 over 2 samples
    again = online_eval.run(db, llm, NOW, feedback=lambda *a, **k: None)
    assert again["turns"] == 0  # evaluated turns are never scored twice


def test_unsampled_turns_are_marked_not_scored(db: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    _turn(db, "What happened?", "abstain")
    monkeypatch.setattr(online_eval, "sampled", lambda *a: False)
    out = online_eval.run(db, lambda *a, **k: None, NOW)
    assert out["sampled"] == 0
    rows = db.execute(select(GuardEvent.guard_id).where(GuardEvent.stage == "online_eval")).scalars().all()
    assert rows == ["online.sampled_out"]
    assert online_eval.run(db, lambda *a, **k: None, NOW)["turns"] == 0


def test_sampling_is_deterministic() -> None:
    ids = [uuid.uuid4() for _ in range(400)]
    picked = [i for i in ids if online_eval.sampled(i, 20)]
    assert picked == [i for i in ids if online_eval.sampled(i, 20)] and 40 < len(picked) < 120
