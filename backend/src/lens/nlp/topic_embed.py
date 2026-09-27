"""Story topics from story centroids (BGE-M3 dense vectors already in Qdrant).

Each topic's prototype is the mean centroid of seed stories: stories whose member articles
all vote for that topic under the keyword rules (`lens.nlp.topic_classifier`). Vectors are
centered on the mean story centroid first. A story takes the nearest prototype's topic when
the cosine clears `min_sim` and beats the runner-up by `min_margin`; otherwise it stays
untagged, since most local crime, accident and court news fits none of the topics.

    python -m lens.nlp.topic_embed build      # write data/topics/prototypes.npz
    python -m lens.nlp.topic_embed backfill   # re-tag every story (Postgres + Qdrant payload)
"""

from __future__ import annotations

import sys
from collections import defaultdict
from functools import lru_cache
from typing import Any

import numpy as np
from qdrant_client import QdrantClient
from qdrant_client.models import ExtendedPointId
from sqlalchemy import update
from sqlalchemy.orm import Session

from lens.core.config_files import load_yaml
from lens.core.settings import REPO_ROOT
from lens.db.models import Story
from lens.nlp.topic_classifier import keyword_votes
from lens.retrieval.qdrant_store import STORIES, fetch_article_vectors, get_qdrant

PROTOTYPES_PATH = REPO_ROOT / "data" / "topics" / "prototypes.npz"


class Prototypes:
    def __init__(self, topics: list[str], matrix: np.ndarray, mean: np.ndarray) -> None:
        self.topics, self.matrix, self.mean = topics, matrix, mean

    def sims(self, vec: np.ndarray) -> np.ndarray:
        v = vec - self.mean
        return np.asarray(self.matrix @ (v / np.linalg.norm(v)))

    def assign(self, vec: np.ndarray, min_sim: float, min_margin: float) -> str | None:
        s = self.sims(vec)
        top2 = np.sort(s)[-2:]
        best = int(np.argmax(s))
        return self.topics[best] if s[best] >= min_sim and top2[1] - top2[0] >= min_margin else None


def _cfg() -> dict[str, Any]:
    cfg: dict[str, Any] = load_yaml("clustering.yaml")["topics"]
    return cfg


def _unit(v: np.ndarray) -> np.ndarray:
    return np.asarray(v / np.linalg.norm(v, axis=-1, keepdims=True))


def seed_ids(session: Session, exclude: frozenset[str] = frozenset()) -> dict[str, list[str]]:
    cfg = _cfg()
    seeds: dict[str, list[str]] = defaultdict(list)
    for sid, votes in sorted(keyword_votes(session).items()):
        if len(votes) == 1 and votes.total() >= cfg["seed_min_votes"] and str(sid) not in exclude:
            (topic,) = votes
            if len(seeds[topic]) < cfg["seed_max_per_topic"]:
                seeds[topic].append(str(sid))
    return seeds


def centroid_mean(client: QdrantClient, n: int) -> np.ndarray:
    points, _ = client.scroll(STORIES, limit=n, with_vectors=["dense"], with_payload=False)
    vecs = [p.vector["dense"] if isinstance(p.vector, dict) else p.vector for p in points]
    return np.asarray(np.mean(np.asarray(vecs, dtype=np.float32), axis=0))


def build_prototypes(
    session: Session, client: QdrantClient, exclude: frozenset[str] = frozenset(), center: bool = True
) -> Prototypes:
    mean = centroid_mean(client, _cfg()["mean_sample"]) if center else np.zeros(1024, dtype=np.float32)
    topics, rows = [], []
    for topic, ids in sorted(seed_ids(session, exclude).items()):
        vecs = np.stack(list(fetch_article_vectors(client, ids, STORIES).values()))
        topics.append(topic)
        rows.append(_unit(_unit(vecs - mean).mean(axis=0)))
    return Prototypes(topics, np.stack(rows), mean)


@lru_cache(maxsize=1)
def load_prototypes() -> Prototypes | None:
    if not PROTOTYPES_PATH.exists():
        return None
    z = np.load(PROTOTYPES_PATH)
    return Prototypes([str(t) for t in z["topics"]], z["matrix"], z["mean"])


def topic_for(centroid: np.ndarray) -> str | None:
    """Topic slug for a story centroid, or None (untagged, or no prototypes for this embedding model)."""
    protos = load_prototypes()
    if protos is None or centroid.shape != protos.mean.shape:
        return None
    cfg = _cfg()
    return protos.assign(centroid, cfg["min_sim"], cfg["min_margin"])


def build() -> None:
    from lens.db.session import get_engine

    with Session(get_engine()) as session:
        p = build_prototypes(session, get_qdrant())
    PROTOTYPES_PATH.parent.mkdir(parents=True, exist_ok=True)
    np.savez(PROTOTYPES_PATH, topics=np.array(p.topics), matrix=p.matrix, mean=p.mean)
    print(f"wrote {PROTOTYPES_PATH} ({', '.join(p.topics)})")


def backfill() -> dict[str, int]:
    from lens.db.session import get_engine

    client = get_qdrant()
    by_topic: dict[str | None, list[ExtendedPointId]] = defaultdict(list)
    offset: Any = None
    while True:
        points, offset = client.scroll(STORIES, limit=1000, offset=offset, with_vectors=["dense"], with_payload=False)
        for p in points:
            vec = p.vector["dense"] if isinstance(p.vector, dict) else p.vector
            by_topic[topic_for(np.asarray(vec, dtype=np.float32))].append(str(p.id))
        if offset is None:
            break
    with Session(get_engine()) as session, session.begin():
        for topic, ids in by_topic.items():
            for i in range(0, len(ids), 5000):
                chunk = ids[i : i + 5000]
                session.execute(update(Story).where(Story.id.in_(chunk)).values(topic=topic))
                client.set_payload(STORIES, payload={"topic": topic}, points=chunk)
    counts = {str(t): len(ids) for t, ids in by_topic.items()}
    print(counts)
    return counts


if __name__ == "__main__":
    {"build": build, "backfill": backfill}[sys.argv[1]]()
