"""Coverage stats and blindspots for one story (docs/01, docs/04 section 11, ADR-0020). Pure code, no I/O.

This is the number users see, so every rule here is explicit and unit-tested. Counts are by
distinct source after syndication dedup: a source that only carries a wire copy of another
article in the story is not counted again. Each source's bias and factuality come from its
third-party rating (outlet level, with provenance); unrated sources are counted as unrated.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Any, Literal

BIAS_BUCKETS = ("left", "center", "right")
FACTUALITY_BUCKETS = ("high", "mixed", "low")

ConfidenceLevel = Literal["low", "medium", "high"]


@dataclass(frozen=True)
class ArticleFacts:
    """What the stats need about one article in the story."""

    source_id: str
    language: str
    is_copy: bool = False  # a syndicated copy of another article in the same story


@dataclass(frozen=True)
class SourceFacts:
    """Provenance-backed rater wording for a source. None means unknown (shown as "Not rated")."""

    bias: str | None = None  # e.g. "Left-Center"
    factuality: str | None = None  # e.g. "Mixed"
    ownership_group: str | None = None


@dataclass
class StoryStatsResult:
    source_count: int
    bias_counts: dict[str, int]
    factuality_counts: dict[str, int]
    ownership_counts: dict[str, int]
    language_counts: dict[str, int]
    coverage_confidence: ConfidenceLevel
    blindspot_type: str | None = None
    blindspot_skew: str | None = None
    blindspot_score: float | None = None


def percentages(counts: list[int]) -> list[int]:
    """Integer percentages summing to 100 (largest remainder). Ties go to the earlier entry.

    Mirrors frontend/src/lib/coverage.ts `percentages`. All zeros when the total is zero."""
    if any(c < 0 for c in counts):
        raise ValueError("counts must be non-negative")
    total = sum(counts)
    if total == 0:
        return [0] * len(counts)
    floors = [c * 100 // total for c in counts]
    remaining = 100 - sum(floors)
    # remainder c*100 % total is the exact fractional part scaled by total: integer math, no float ties
    order = sorted(range(len(counts)), key=lambda i: (-(counts[i] * 100 % total), i))
    for i in order[:remaining]:
        floors[i] += 1
    return floors


def bucket(wording: str | None, value_map: dict[str, str], buckets: tuple[str, ...]) -> str:
    """Rater wording -> bucket via config. Unknown or missing wording is "unrated", never guessed."""
    b = value_map.get((wording or "").strip().lower())
    return b if b in buckets else "unrated"


def rated_share_confidence(counts: dict[str, int], cfg: dict[str, Any]) -> ConfidenceLevel:
    """How far a count split can be trusted: the share of sources that are actually rated.
    `cfg` is `stats.rated_share_confidence` in config/guardrails.yaml."""
    total = sum(counts.values())
    rated = total - counts.get("unrated", 0)
    share = rated / total if total else 0.0
    if share >= cfg["high_min_rated_share"]:
        return "high"
    if share >= cfg["medium_min_rated_share"]:
        return "medium"
    return "low"


def _language_group(lang: str, groups: dict[str, list[str]]) -> str:
    base = lang.split("-")[0]
    return next((g for g, langs in groups.items() if base in langs), "indic")


def compute_story_stats(
    articles: list[ArticleFacts],
    sources: dict[str, SourceFacts],
    min_sources_for_blindspot: int,
    cfg: dict[str, Any],
) -> StoryStatsResult:
    """`cfg` is the `stats` section of config/guardrails.yaml."""
    by_source: dict[str, list[ArticleFacts]] = {}
    for a in articles:
        if not a.is_copy:
            by_source.setdefault(a.source_id, []).append(a)
    n = len(by_source)

    bias_counts = {b: 0 for b in (*BIAS_BUCKETS, "unrated")}
    factuality_counts = {b: 0 for b in (*FACTUALITY_BUCKETS, "unrated")}
    ownership: Counter[str] = Counter()
    for s in by_source:
        facts = sources.get(s, SourceFacts())
        bias_counts[bucket(facts.bias, cfg["bias_value_map"], BIAS_BUCKETS)] += 1
        factuality_counts[bucket(facts.factuality, cfg["factuality_value_map"], FACTUALITY_BUCKETS)] += 1
        ownership[facts.ownership_group or "unknown"] += 1

    # A source's language is the most common language of its articles in this story.
    lang_of = {s: Counter(a.language for a in arts).most_common(1)[0][0] for s, arts in by_source.items()}

    result = StoryStatsResult(
        source_count=n,
        bias_counts=bias_counts,
        factuality_counts=factuality_counts,
        ownership_counts=dict(ownership),
        language_counts=dict(Counter(lang_of.values())),
        coverage_confidence=rated_share_confidence(bias_counts, cfg["rated_share_confidence"]),
    )

    # Bias blindspot first: >= share of *rated* sources on one side, with enough rated sources.
    rated = {b: bias_counts[b] for b in BIAS_BUCKETS}
    n_rated = sum(rated.values())
    if n_rated >= min_sources_for_blindspot:
        top, top_n = max(rated.items(), key=lambda kv: kv[1])
        share = top_n / n_rated
        if share >= cfg["blindspot_bias_share"]:
            result.blindspot_type, result.blindspot_skew, result.blindspot_score = "bias", top, round(share, 4)
            return result

    # Language blindspot: nearly all sources in one language group.
    if n >= min_sources_for_blindspot:
        groups = Counter(_language_group(lang, cfg["language_groups"]) for lang in lang_of.values())
        top_group, top_n = groups.most_common(1)[0]
        share = top_n / n
        if share >= cfg["blindspot_language_share"]:
            result.blindspot_type, result.blindspot_skew, result.blindspot_score = (
                "language",
                top_group,
                round(share, 4),
            )
    return result
