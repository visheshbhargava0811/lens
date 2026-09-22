import math

import pytest

from lens.evals.clustering import (
    GoldArticle,
    bcubed,
    cross_lingual_pairs,
    hard_negative_merges,
    merge_error_rate,
    score,
)


def test_bcubed_perfect_all_merged_and_all_split() -> None:
    gold = ["a", "a", "b", "b", "b"]
    assert bcubed(gold, gold) == (1.0, 1.0, 1.0)
    p, r, _ = bcubed(gold, ["x"] * 5)  # everything in one cluster
    assert r == 1.0 and p == pytest.approx((2 * 2 / 5 + 3 * 3 / 5) / 5)
    p, r, _ = bcubed(gold, [str(i) for i in range(5)])  # all singletons
    assert p == 1.0 and r == pytest.approx((2 * 1 / 2 + 3 * 1 / 3) / 5)


def test_bcubed_hand_computed() -> None:
    # gold {1,2,3} {4,5}; pred {1,2} {3,4,5}
    gold, pred = ["a", "a", "a", "b", "b"], ["x", "x", "y", "y", "y"]
    p, r, f = bcubed(gold, pred)
    # precision per item: 1,1,1/3,2/3,2/3 ; recall: 2/3,2/3,1/3,1,1
    assert p == pytest.approx((1 + 1 + 1 / 3 + 2 / 3 + 2 / 3) / 5)
    assert r == pytest.approx((2 / 3 + 2 / 3 + 1 / 3 + 1 + 1) / 5)
    assert f == pytest.approx(2 * p * r / (p + r))


def test_cross_lingual_pairs_only_counts_different_languages() -> None:
    gold = ["a", "a", "a", "b"]
    langs = ["en", "hi", "hi-Latn", "en"]  # hi and hi-Latn are the same language family
    res = cross_lingual_pairs(gold, ["x", "x", "y", "y"], langs)
    # cross-lingual gold pairs: (0,1), (0,2) -> (0,1) together, (0,2) apart
    assert res["pairs_gold"] == 2 and res["recall"] == 0.5
    # predicted-together cross-lingual pairs: (0,1) true, (2,3) false
    assert res["precision"] == 0.5
    assert math.isnan(cross_lingual_pairs(["a"], ["x"], ["en"])["recall"])


def test_merge_error_rate() -> None:
    assert merge_error_rate(["a", "a", "b", "c"], ["x", "x", "y", "y"]) == 0.5
    assert merge_error_rate(["a", "b"], ["x", "y"]) == 0.0


def _g(i: int, story: str, lang: str = "en", hng: str | None = None) -> GoldArticle:
    return GoldArticle(str(i), story, lang, "s", "2026-09-21T00:00:00Z", "t", None, hng)


def test_hard_negative_merges_and_score() -> None:
    gold = [_g(0, "flood-assam", hng="floods"), _g(1, "flood-kerala", hng="floods"), _g(2, "budget")]
    assert hard_negative_merges(gold, ["x", "x", "y"]) == 1
    assert hard_negative_merges(gold, ["x", "y", "z"]) == 0
    s = score(gold, ["x", "y", "z"], verifier_calls=1)
    assert s["bcubed_f1"] == 1.0 and s["ari"] == 1.0 and s["verifier_call_rate"] == pytest.approx(0.3333, abs=1e-4)
