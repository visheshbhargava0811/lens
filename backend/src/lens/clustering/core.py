"""Incremental event clustering (docs/04 section 5). Pure logic: no database, no Qdrant.

The same code runs in the eval (in memory, over a labeled set) and in the pipeline (with stories
loaded from Postgres/Qdrant), so eval numbers describe what production does.
"""

from __future__ import annotations

import math
import uuid
from collections import Counter
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Literal

import numpy as np

Decision = Literal["assign", "verify", "new"]


@dataclass
class ArticleFeatures:
    id: str
    vector: np.ndarray  # L2-normalized article vector
    published_at: datetime
    entities: frozenset[str] | None = None  # normalized entity keys; None = not extracted yet
    event_type: str | None = None


@dataclass
class StoryState:
    id: str
    centroid: np.ndarray  # running mean of member vectors (not normalized)
    n: int
    first_seen_at: datetime
    last_updated_at: datetime
    entities: Counter[str] = field(default_factory=Counter)
    event_types: Counter[str] = field(default_factory=Counter)
    members: list[str] = field(default_factory=list)

    def unit_centroid(self) -> np.ndarray:
        norm = float(np.linalg.norm(self.centroid))
        return self.centroid / norm if norm > 0 else self.centroid

    def add(self, a: ArticleFeatures) -> None:
        self.centroid = self.centroid + (a.vector - self.centroid) / (self.n + 1)
        self.n += 1
        self.last_updated_at = max(self.last_updated_at, a.published_at)
        if a.entities:
            self.entities.update(a.entities)
        if a.event_type:
            self.event_types[a.event_type] += 1
        self.members.append(a.id)


@dataclass(frozen=True)
class Scored:
    story_id: str
    score: float
    parts: dict[str, float]


def combined_score(a: ArticleFeatures, s: StoryState, cfg: dict[str, Any]) -> Scored:
    """S = sum(w_i * f_i) / sum(w_i) over the features available for this pair."""
    w = cfg["weights"]
    parts: dict[str, float] = {"cos": float(a.vector @ s.unit_centroid())}
    if a.entities is not None and s.entities:
        story_ents = set(s.entities)
        union = a.entities | story_ents
        parts["entity_jaccard"] = len(a.entities & story_ents) / len(union) if union else 0.0
    if w.get("time", 0):
        hours = abs((a.published_at - s.last_updated_at).total_seconds()) / 3600
        parts["time"] = math.exp(-hours / cfg["time_decay_hours"])
    if a.event_type and s.event_types:
        parts["event_type"] = 1.0 if s.event_types.most_common(1)[0][0] == a.event_type else 0.0
    total_w = sum(w[k] for k in parts)
    score = sum(w[k] * v for k, v in parts.items()) / total_w if total_w else parts["cos"]
    return Scored(s.id, score, parts)


def decide(score: float, cfg: dict[str, Any]) -> Decision:
    t = cfg["thresholds"]
    if score >= t["high"]:
        return "assign"
    if score >= t["low"]:
        return "verify"
    return "new"


Verifier = Callable[[ArticleFeatures, StoryState, Scored], Literal["yes", "no", "uncertain"]]


@dataclass
class Outcome:
    article_id: str
    story_id: str
    decision: Decision
    best: Scored | None
    verifier_called: bool
    verifier_verdict: str | None = None


class IncrementalClusterer:
    """Assigns articles one at a time, in publication order, to open stories in the time window."""

    def __init__(
        self,
        cfg: dict[str, Any],
        verifier: Verifier | None = None,
        id_factory: Callable[[], str] | None = None,
    ):
        self.cfg = cfg
        self.verifier = verifier
        self.stories: dict[str, StoryState] = {}
        self._new_id = id_factory or (lambda: str(uuid.uuid4()))

    def candidates(self, a: ArticleFeatures) -> list[StoryState]:
        window = timedelta(hours=self.cfg["window_hours"])
        open_ = [s for s in self.stories.values() if a.published_at - s.last_updated_at <= window]
        if not open_:
            return []
        mat = np.stack([s.unit_centroid() for s in open_])
        order = np.argsort(-(mat @ a.vector))[: self.cfg["candidates"]]
        return [open_[i] for i in order]

    def add(self, a: ArticleFeatures) -> Outcome:
        scored = sorted((combined_score(a, s, self.cfg) for s in self.candidates(a)), key=lambda x: -x.score)
        best = scored[0] if scored else None
        decision: Decision = decide(best.score, self.cfg) if best else "new"
        called, verdict = False, None
        target: str | None = best.story_id if best and decision == "assign" else None
        if best and decision == "verify":
            called = True
            if self.verifier is not None:
                verdict = self.verifier(a, self.stories[best.story_id], best)
                target = best.story_id if verdict == "yes" else None
            elif self.cfg["borderline_without_verifier"] == "assign":
                target = best.story_id
        if target is None:
            target = self._new_id()
            self.stories[target] = StoryState(target, np.zeros_like(a.vector), 0, a.published_at, a.published_at)
        self.stories[target].add(a)
        return Outcome(a.id, target, decision, best, called, verdict)

    def run(self, articles: Iterable[ArticleFeatures]) -> list[Outcome]:
        return [self.add(a) for a in sorted(articles, key=lambda x: (x.published_at, x.id))]
