"""Coverage math edge cases (Phase 3 acceptance, ADR-0020): ties, rounding to 100, unrated
outlets, syndication dedup, below min_sources, rater wording, and both blindspot types."""

from typing import Any

import pytest

from lens.core.config_files import load_yaml
from lens.stats.coverage import (
    BIAS_BUCKETS,
    ArticleFacts,
    SourceFacts,
    bucket,
    compute_story_stats,
    percentages,
    rated_share_confidence,
)

CFG: dict[str, Any] = load_yaml("guardrails.yaml")["stats"]
MIN_BLIND = load_yaml("guardrails.yaml")["min_sources_for_blindspot"]


def _a(src: str, lang: str = "en", copy: bool = False) -> ArticleFacts:
    return ArticleFacts(source_id=src, language=lang, is_copy=copy)


def _rated(**bias_by_source: str) -> dict[str, SourceFacts]:
    return {s: SourceFacts(bias=b) for s, b in bias_by_source.items()}


@pytest.mark.parametrize(
    ("counts", "expected"),
    [
        ([1, 1, 1], [34, 33, 33]),  # three-way tie: the extra point goes to the first
        ([2, 1], [67, 33]),
        ([0, 0, 0], [0, 0, 0]),
        ([5], [100]),
        ([1, 1, 1, 1, 1, 1, 1], [15, 15, 14, 14, 14, 14, 14]),
        ([18, 12, 9, 3], [43, 29, 21, 7]),  # the docs/09 example
    ],
)
def test_percentages_sum_to_100_and_break_ties_to_earlier(counts: list[int], expected: list[int]) -> None:
    got = percentages(counts)
    assert got == expected
    assert sum(got) in (0, 100)


def test_percentages_reject_negative() -> None:
    with pytest.raises(ValueError):
        percentages([1, -1])


@pytest.mark.parametrize(
    ("wording", "expected"),
    [
        ("Left-Center", "left"),  # lean-left counts as Left (ADR-0020)
        ("RIGHT-CENTER", "right"),
        ("Least Biased", "center"),
        ("Extreme Right", "right"),
        ("Pro-Science", "unrated"),  # unknown wording is never guessed
        (None, "unrated"),
        ("", "unrated"),
    ],
)
def test_bias_wording_maps_to_buckets(wording: str | None, expected: str) -> None:
    assert bucket(wording, CFG["bias_value_map"], BIAS_BUCKETS) == expected


def test_counts_are_by_distinct_source_after_syndication_dedup() -> None:
    arts = [_a("s1"), _a("s1"), _a("s2"), _a("s3", copy=True)]  # s3 only carries a wire copy
    r = compute_story_stats(arts, _rated(s1="Left-Center", s2="Right-Center", s3="Left"), MIN_BLIND, CFG)
    assert r.source_count == 2
    assert r.bias_counts == {"left": 1, "center": 0, "right": 1, "unrated": 0}


def test_unknown_facts_are_unrated_and_unknown() -> None:
    sources = {"s1": SourceFacts(bias="Least Biased", factuality="High", ownership_group="Group A")}
    r = compute_story_stats([_a("s1"), _a("s2")], sources, MIN_BLIND, CFG)
    assert r.bias_counts == {"left": 0, "center": 1, "right": 0, "unrated": 1}
    assert r.factuality_counts == {"high": 1, "mixed": 0, "low": 0, "unrated": 1}
    assert r.ownership_counts == {"Group A": 1, "unknown": 1}


def test_factuality_wording_maps_conservatively() -> None:
    sources = {
        "s1": SourceFacts(factuality="Very High"),
        "s2": SourceFacts(factuality="Mostly Factual"),  # counts as mixed (ADR-0019)
        "s3": SourceFacts(factuality="Very Low"),
        "s4": SourceFacts(factuality="Satire"),
    }
    r = compute_story_stats([_a(s) for s in sources], sources, MIN_BLIND, CFG)
    assert r.factuality_counts == {"high": 1, "mixed": 1, "low": 1, "unrated": 1}


def test_all_unrated_is_low_confidence_and_never_a_bias_blindspot() -> None:
    arts = [_a(f"s{i}", lang="en" if i % 2 else "hi") for i in range(12)]
    r = compute_story_stats(arts, {}, MIN_BLIND, CFG)
    assert r.coverage_confidence == "low"
    assert r.blindspot_type is None
    assert r.bias_counts["unrated"] == 12


@pytest.mark.parametrize(
    ("counts", "expected"),
    [
        ({"left": 0, "center": 0, "right": 0, "unrated": 5}, "low"),
        ({"left": 0, "center": 0, "right": 0, "unrated": 0}, "low"),
        ({"left": 2, "center": 1, "right": 0, "unrated": 2}, "medium"),  # 60% rated
        ({"left": 2, "center": 0, "right": 2, "unrated": 1}, "high"),  # 80% rated, at threshold
    ],
)
def test_confidence_follows_rated_share(counts: dict[str, int], expected: str) -> None:
    assert rated_share_confidence(counts, CFG["rated_share_confidence"]) == expected


def test_below_min_rated_sources_has_no_bias_blindspot() -> None:
    sources = _rated(**{f"s{i}": "Right" for i in range(MIN_BLIND - 1)})
    r = compute_story_stats([_a(s) for s in sources], sources, MIN_BLIND, CFG)
    assert r.blindspot_type != "bias"


def test_bias_blindspot_at_threshold() -> None:
    n = 10
    k = round(n * CFG["blindspot_bias_share"])  # exactly at the share
    sources = _rated(**{f"s{i}": "Right-Center" if i < k else "Left-Center" for i in range(n)})
    r = compute_story_stats([_a(s) for s in sources], sources, MIN_BLIND, CFG)
    assert (r.blindspot_type, r.blindspot_skew) == ("bias", "right")
    assert r.blindspot_score == pytest.approx(k / n)
    assert r.coverage_confidence == "high"


def test_bias_share_counts_only_rated_sources() -> None:
    # 7 right + 3 left rated, 3 unrated: 70% of rated sources is a blindspot; 10/13 rated is medium.
    sources = _rated(**{f"r{i}": "Right" for i in range(7)}, **{f"l{i}": "Left" for i in range(3)})
    arts = [_a(s) for s in sources] + [_a(f"u{i}") for i in range(3)]
    r = compute_story_stats(arts, sources, MIN_BLIND, CFG)
    assert (r.blindspot_type, r.blindspot_skew) == ("bias", "right")
    assert r.coverage_confidence == "medium"


def test_bias_just_below_threshold_is_not_a_blindspot() -> None:
    sources = _rated(**{f"s{i}": "Right" if i < 6 else "Left" for i in range(10)})  # 60%
    assert compute_story_stats([_a(s) for s in sources], sources, MIN_BLIND, CFG).blindspot_type != "bias"


def test_language_blindspot_when_one_group_dominates() -> None:
    arts = [_a(f"s{i}", lang="hi" if i < 9 else "mr") for i in range(10)]
    r = compute_story_stats(arts, {}, MIN_BLIND, CFG)
    assert (r.blindspot_type, r.blindspot_skew) == ("language", "indic")
    assert r.language_counts == {"hi": 9, "mr": 1}


def test_language_share_just_below_threshold() -> None:
    arts = [_a(f"s{i}", lang="en" if i < 8 else "hi") for i in range(10)]  # 80% English
    assert compute_story_stats(arts, {}, MIN_BLIND, CFG).blindspot_type is None


def test_empty_story() -> None:
    r = compute_story_stats([], {}, MIN_BLIND, CFG)
    assert r.source_count == 0 and r.coverage_confidence == "low" and r.blindspot_type is None
