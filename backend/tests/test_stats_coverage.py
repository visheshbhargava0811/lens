"""Coverage math edge cases (Phase 3 acceptance): ties, rounding to 100, unclassified,
syndication dedup, below min_sources, and both blindspot types."""

from typing import Any

import pytest

from lens.core.config_files import load_yaml
from lens.stats.coverage import ArticleFacts, SourceFacts, compute_story_stats, factuality_confidence, percentages

CFG: dict[str, Any] = load_yaml("guardrails.yaml")["stats"]
MIN_BLIND = load_yaml("guardrails.yaml")["min_sources_for_blindspot"]


def _a(
    src: str, stance: str = "unclassified", conf: str | None = "high", lang: str = "en", copy: bool = False
) -> ArticleFacts:
    return ArticleFacts(source_id=src, language=lang, is_copy=copy, stance=stance, stance_confidence=conf)


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


def test_counts_are_by_distinct_source_after_syndication_dedup() -> None:
    arts = [
        _a("s1", "critical"),
        _a("s1", "critical"),  # two articles, one source
        _a("s2", "supportive"),
        _a("s3", "critical", copy=True),  # carries only a wire copy: not counted again
    ]
    r = compute_story_stats(arts, {}, MIN_BLIND, CFG)
    assert r.source_count == 2
    assert r.stance_counts == {"critical": 1, "balanced": 0, "supportive": 1, "unclassified": 0}


def test_low_confidence_and_not_applicable_count_as_unclassified() -> None:
    arts = [_a("s1", "critical", conf="low"), _a("s2", "not_applicable"), _a("s3", "balanced")]
    r = compute_story_stats(arts, {}, MIN_BLIND, CFG)
    assert r.stance_counts["unclassified"] == 2 and r.stance_counts["balanced"] == 1
    assert sum(r.stance_pct.values()) == 100


def test_source_with_tied_article_stances_is_unclassified() -> None:
    r = compute_story_stats([_a("s1", "critical"), _a("s1", "supportive")], {}, MIN_BLIND, CFG)
    assert r.stance_counts["unclassified"] == 1


def test_unknown_facts_are_unrated_and_unknown() -> None:
    sources = {"s1": SourceFacts(factuality="High", ownership_group="Group A")}
    r = compute_story_stats([_a("s1"), _a("s2")], sources, MIN_BLIND, CFG)
    assert r.factuality_counts == {"high": 1, "mixed": 0, "low": 0, "unrated": 1}
    assert r.ownership_counts == {"Group A": 1, "unknown": 1}


def test_all_unclassified_is_low_confidence_and_never_a_stance_blindspot() -> None:
    # Phase 3 stub stance: nothing classified. Must not produce a stance figure with false confidence.
    arts = [_a(f"s{i}", conf=None, lang="en" if i % 2 else "hi") for i in range(12)]
    r = compute_story_stats(arts, {}, MIN_BLIND, CFG)
    assert r.coverage_confidence == "low"
    assert r.blindspot_type is None
    assert r.stance_pct["unclassified"] == 100


def test_below_min_sources_has_no_blindspot() -> None:
    arts = [_a(f"s{i}", "supportive") for i in range(MIN_BLIND - 1)]
    r = compute_story_stats(arts, {}, MIN_BLIND, CFG)
    assert r.blindspot_type is None
    assert r.coverage_confidence == "medium"  # fully classified but too few sources for high


def test_stance_blindspot_at_threshold() -> None:
    n = 10
    k = round(n * CFG["blindspot_stance_share"])  # exactly at the share
    arts = [_a(f"s{i}", "supportive" if i < k else "critical") for i in range(n)]
    r = compute_story_stats(arts, {}, MIN_BLIND, CFG)
    assert (r.blindspot_type, r.blindspot_skew) == ("stance", "supportive")
    assert r.blindspot_score == pytest.approx(k / n)
    assert r.coverage_confidence == "high"


def test_stance_just_below_threshold_is_not_a_blindspot() -> None:
    arts = [_a(f"s{i}", "supportive" if i < 6 else "critical") for i in range(10)]  # 60%
    assert compute_story_stats(arts, {}, MIN_BLIND, CFG).blindspot_type != "stance"


def test_language_blindspot_when_one_group_dominates() -> None:
    # 9 Hindi + 1 Marathi + 0 English: Indian-language group is 100%, English near zero.
    arts = [_a(f"s{i}", lang="hi" if i < 9 else "mr") for i in range(10)]
    r = compute_story_stats(arts, {}, MIN_BLIND, CFG)
    assert (r.blindspot_type, r.blindspot_skew) == ("language", "indic")
    assert r.language_counts == {"hi": 9, "mr": 1}


def test_language_share_just_below_threshold() -> None:
    arts = [_a(f"s{i}", lang="en" if i < 8 else "hi") for i in range(10)]  # 80% English
    assert compute_story_stats(arts, {}, MIN_BLIND, CFG).blindspot_type is None


def test_mixed_languages_are_not_a_language_blindspot() -> None:
    arts = [_a(f"s{i}", lang="en" if i < 5 else "hi") for i in range(8)]
    assert compute_story_stats(arts, {}, MIN_BLIND, CFG).blindspot_type is None


def test_empty_story() -> None:
    r = compute_story_stats([], {}, MIN_BLIND, CFG)
    assert r.source_count == 0 and r.coverage_confidence == "low" and r.blindspot_type is None


@pytest.mark.parametrize(
    ("counts", "expected"),
    [
        ({"high": 0, "mixed": 0, "low": 0, "unrated": 5}, "low"),  # nothing rated yet (rule 7)
        ({"high": 0, "mixed": 0, "low": 0, "unrated": 0}, "low"),
        ({"high": 2, "mixed": 1, "low": 0, "unrated": 2}, "medium"),  # 60% rated
        ({"high": 4, "mixed": 0, "low": 0, "unrated": 1}, "high"),  # 80% rated, at threshold
    ],
)
def test_factuality_confidence_follows_rated_share(counts: dict[str, int], expected: str) -> None:
    assert factuality_confidence(counts, CFG["factuality_confidence"]) == expected
