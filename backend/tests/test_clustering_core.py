from datetime import UTC, datetime, timedelta
from typing import Any

import numpy as np
import pytest

from lens.clustering.core import ArticleFeatures, IncrementalClusterer, combined_score, decide

T0 = datetime(2026, 9, 21, 6, 0, tzinfo=UTC)
CFG: dict[str, Any] = {
    "window_hours": 72,
    "candidates": 5,
    "time_decay_hours": 24,
    "weights": {"cos": 0.6, "entity_jaccard": 0.2, "time": 0.1, "event_type": 0.1},
    "thresholds": {"high": 0.82, "low": 0.68},
    "borderline_without_verifier": "new_story",
}


def _v(*xs: float) -> np.ndarray:
    v = np.array(xs, dtype=np.float32)
    return v / np.linalg.norm(v)


def _a(i: str, vec: np.ndarray, hours: float = 0, **kw: Any) -> ArticleFeatures:
    return ArticleFeatures(i, vec, T0 + timedelta(hours=hours), **kw)


def test_similar_articles_join_and_different_ones_split() -> None:
    c = IncrementalClusterer(CFG, id_factory=iter(["s1", "s2", "s3"]).__next__)
    out = c.run([_a("a", _v(1, 0, 0)), _a("b", _v(0.99, 0.1, 0), 1), _a("c", _v(0, 1, 0), 2)])
    assert [o.story_id for o in out] == ["s1", "s1", "s2"]
    assert out[1].decision == "assign" and out[2].decision == "new"


def test_window_closes_old_stories() -> None:
    c = IncrementalClusterer(CFG, id_factory=iter(["s1", "s2"]).__next__)
    out = c.run([_a("a", _v(1, 0)), _a("b", _v(1, 0), hours=80)])
    assert out[0].story_id != out[1].story_id


def test_borderline_policy_and_verifier() -> None:
    # cos 0.75, same hour: S = (0.6*0.75 + 0.1*1.0) / 0.7 = 0.786, between the thresholds
    borderline = [_a("a", _v(1, 0)), _a("b", _v(0.75, 0.6614), 0)]
    c = IncrementalClusterer(CFG, id_factory=iter(["s1", "s2"]).__next__)
    out = c.run(borderline)
    assert out[1].decision == "verify" and out[1].verifier_called and out[1].story_id == "s2"

    c = IncrementalClusterer({**CFG, "borderline_without_verifier": "assign"}, id_factory=iter(["s1", "s2"]).__next__)
    assert c.run(borderline)[1].story_id == "s1"

    c = IncrementalClusterer(CFG, verifier=lambda a, s, sc: "yes", id_factory=iter(["s1", "s2"]).__next__)
    out = c.run(borderline)
    assert out[1].story_id == "s1" and out[1].verifier_verdict == "yes"


def test_score_reweights_over_available_features() -> None:
    c = IncrementalClusterer(CFG, id_factory=iter(["s1"]).__next__)
    c.run([_a("a", _v(1, 0))])
    s = c.stories["s1"]
    dense_only = combined_score(_a("b", _v(1, 0)), s, CFG)
    assert set(dense_only.parts) == {"cos", "time"}
    assert dense_only.score == pytest.approx(1.0)
    with_ents = combined_score(_a("b", _v(1, 0), entities=frozenset({"x"})), s, CFG)
    assert "entity_jaccard" not in with_ents.parts  # story has no entities yet


def test_decide_thresholds() -> None:
    assert (decide(0.9, CFG), decide(0.7, CFG), decide(0.5, CFG)) == ("assign", "verify", "new")
