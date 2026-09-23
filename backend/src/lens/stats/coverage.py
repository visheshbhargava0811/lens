"""Coverage stats and blindspots for one story (docs/01, docs/04 section 11). Pure code, no I/O.

This is the number users see, so every rule here is explicit and unit-tested. Counts are by
distinct source after syndication dedup: a source that only carries a wire copy of another
article in the story is not counted again.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Literal

STANCE_BUCKETS = ("critical", "balanced", "supportive")
FACTUALITY_BUCKETS = ("high", "mixed", "low")
_CONF_RANK = {"low": 1, "medium": 2, "high": 3}

ConfidenceLevel = Literal["low", "medium", "high"]


@dataclass(frozen=True)
class ArticleFacts:
    """What the stats need about one article in the story."""

    source_id: str
    language: str
    is_copy: bool = False  # a syndicated copy of another article (original_article_id set)
    stance: str = "unclassified"  # critical | balanced | supportive | not_applicable | unclassified
    stance_confidence: str | None = None  # low | medium | high


@dataclass(frozen=True)
class SourceFacts:
    """Provenance-backed facts about a source. None means unknown (shown as "Not rated")."""

    factuality: str | None = None  # high | mixed | low
    ownership_group: str | None = None


@dataclass
class StoryStatsResult:
    source_count: int
    stance_counts: dict[str, int]
    factuality_counts: dict[str, int]
    ownership_counts: dict[str, int]
    language_counts: dict[str, int]
    coverage_confidence: ConfidenceLevel
    blindspot_type: str | None = None
    blindspot_skew: str | None = None
    blindspot_score: float | None = None
    stance_pct: dict[str, int] = field(default_factory=dict)


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


def _source_stance(articles: list[ArticleFacts]) -> str:
    """One stance per source. Low-confidence stances count as unclassified (docs/01).
    If a source's articles disagree, the most common stance wins; a tie is unclassified."""
    votes = Counter(
        a.stance for a in articles if a.stance in STANCE_BUCKETS and a.stance_confidence in ("medium", "high")
    )
    if not votes:
        return "unclassified"
    ranked = votes.most_common()
    if len(ranked) > 1 and ranked[0][1] == ranked[1][1]:
        return "unclassified"
    return ranked[0][0]


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

    stance_of = {s: _source_stance(arts) for s, arts in by_source.items()}
    stance_counts = {b: 0 for b in (*STANCE_BUCKETS, "unclassified")}
    for st in stance_of.values():
        stance_counts[st if st in STANCE_BUCKETS else "unclassified"] += 1
    stance_pct = dict(zip(stance_counts, percentages(list(stance_counts.values())), strict=True))

    factuality_counts = {b: 0 for b in (*FACTUALITY_BUCKETS, "unrated")}
    ownership: Counter[str] = Counter()
    for s in by_source:
        facts = sources.get(s, SourceFacts())
        f = (facts.factuality or "").lower()
        factuality_counts[f if f in FACTUALITY_BUCKETS else "unrated"] += 1
        ownership[facts.ownership_group or "unknown"] += 1

    # A source's language is the most common language of its articles in this story.
    lang_of = {s: Counter(a.language for a in arts).most_common(1)[0][0] for s, arts in by_source.items()}
    language_counts = dict(Counter(lang_of.values()))

    unclassified_share = stance_counts["unclassified"] / n if n else 1.0
    stance_confs = [
        _CONF_RANK[a.stance_confidence]
        for arts in by_source.values()
        for a in arts
        if a.stance_confidence in _CONF_RANK
    ]
    avg_conf = sum(stance_confs) / len(stance_confs) if stance_confs else 0.0
    c = cfg["confidence"]
    confidence: ConfidenceLevel
    if n < 1 or unclassified_share > c["low_max_unclassified"] or avg_conf < _CONF_RANK["medium"]:
        confidence = "low"
    elif n >= c["high_min_sources"] and unclassified_share <= c["high_max_unclassified"]:
        confidence = "high"
    else:
        confidence = "medium"

    result = StoryStatsResult(
        source_count=n,
        stance_counts=stance_counts,
        factuality_counts=factuality_counts,
        ownership_counts=dict(ownership),
        language_counts=language_counts,
        coverage_confidence=confidence,
        stance_pct=stance_pct,
    )

    # Stance blindspot first: >= share of *classified* sources in one bucket, with enough sources.
    classified = {b: stance_counts[b] for b in STANCE_BUCKETS}
    n_classified = sum(classified.values())
    if n_classified >= min_sources_for_blindspot:
        top, top_n = max(classified.items(), key=lambda kv: kv[1])
        share = top_n / n_classified
        if share >= cfg["blindspot_stance_share"]:
            result.blindspot_type, result.blindspot_skew, result.blindspot_score = "stance", top, round(share, 4)
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


def factuality_confidence(counts: dict[str, int], cfg: dict[str, Any]) -> ConfidenceLevel:
    """How much the factuality mix can be trusted: the share of sources that are actually rated.
    `cfg` is `stats.factuality_confidence` in config/guardrails.yaml."""
    total = sum(counts.values())
    rated = total - counts.get("unrated", 0)
    share = rated / total if total else 0.0
    if share >= cfg["high_min_rated_share"]:
        return "high"
    if share >= cfg["medium_min_rated_share"]:
        return "medium"
    return "low"
