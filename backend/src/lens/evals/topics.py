"""Topic tagging eval: keyword rules vs centroid prototypes on data/evals/topics/gold_v1.jsonl.

Each gold story lists its acceptable labels ("none" = fits no topic). Thresholds are tuned
on half A (even rows) for topical F1 and reported on held-out half B. Gold stories are
excluded from the prototype seeds. Writes reports/topics_<name>.md and .json.

    python -m lens.evals.topics --name v1
"""

from __future__ import annotations

import argparse
import json
import uuid
from collections import Counter
from typing import Any

import numpy as np
from sqlalchemy.orm import Session

from lens.core.settings import REPO_ROOT
from lens.db.session import get_engine
from lens.nlp.topic_classifier import keyword_votes, vote_winner
from lens.nlp.topic_embed import build_prototypes
from lens.retrieval.qdrant_store import STORIES, fetch_article_vectors, get_qdrant

GOLD = REPO_ROOT / "data" / "evals" / "topics" / "gold_v1.jsonl"
SIMS = np.round(np.arange(-0.2, 0.8, 0.02), 2)
MARGINS = [0.0, 0.01, 0.02, 0.03, 0.05, 0.08, 0.12]


def score(preds: list[str | None], gold: list[list[str]]) -> dict[str, float]:
    """accuracy (untagged counts as "none"), topical precision/recall/F1, coverage."""
    hits = [(p or "none") in g for p, g in zip(preds, gold, strict=True)]
    tagged = [h for p, h in zip(preds, hits, strict=True) if p]
    topical = [h for g, h in zip(gold, hits, strict=True) if g[0] != "none"]
    prec = sum(tagged) / len(tagged) if tagged else 0.0
    rec = sum(topical) / len(topical) if topical else 0.0
    return {
        "accuracy": sum(hits) / len(hits),
        "precision": prec,
        "recall": rec,
        "f1": 2 * prec * rec / (prec + rec) if prec + rec else 0.0,
        "coverage": len(tagged) / len(preds),
    }


def _assign(s: np.ndarray, topics: list[str], min_sim: float, margin: float) -> str | None:
    top2 = np.sort(s)[-2:]
    return topics[int(np.argmax(s))] if s.max() >= min_sim and top2[1] - top2[0] >= margin else None


def run(name: str) -> dict[str, Any]:
    gold = [json.loads(line) for line in GOLD.read_text(encoding="utf-8").splitlines() if line.strip()]
    ids = [g["inputs"]["story_id"] for g in gold]
    labels = [g["reference_outputs"]["labels"] for g in gold]
    halves = {"A": list(range(0, len(gold), 2)), "B": list(range(1, len(gold), 2)), "all": list(range(len(gold)))}
    client = get_qdrant()
    vecs = fetch_article_vectors(client, ids, STORIES)
    with Session(get_engine()) as session:
        votes = keyword_votes(session, ids)
        kw = [vote_winner(votes.get(uuid.UUID(i), Counter())) for i in ids]
        results: dict[str, Any] = {
            "n": len(gold),
            "keyword": {h: score([kw[i] for i in ix], [labels[i] for i in ix]) for h, ix in halves.items()},
        }
        for center in (False, True):
            protos = build_prototypes(session, client, exclude=frozenset(ids), center=center)
            sims = [protos.sims(vecs[i]) for i in ids]

            def preds(
                ms: float, mg: float, ix: list[int], sims: list[np.ndarray] = sims, topics: list[str] = protos.topics
            ) -> list[str | None]:
                return [_assign(sims[i], topics, ms, mg) for i in ix]

            best = max(
                ((float(ms), mg) for ms in SIMS for mg in MARGINS),
                key=lambda p: score(preds(p[0], p[1], halves["A"]), [labels[i] for i in halves["A"]])["f1"],
            )
            results["centered" if center else "raw"] = {
                "min_sim": float(best[0]),
                "min_margin": best[1],
                **{h: score(preds(best[0], best[1], ix), [labels[i] for i in ix]) for h, ix in halves.items()},
            }
    out = REPO_ROOT / "reports" / f"topics_{name}"
    out.with_suffix(".json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    out.with_suffix(".md").write_text(render(results), encoding="utf-8")
    print(render(results))
    return results


def render(r: dict[str, Any]) -> str:
    lines = [
        f"# Topic tagging eval ({r['n']} stories, data/evals/topics/gold_v1.jsonl)",
        "",
        "Gold labels are Claude-drafted and owner-reviewed 2026-09-27 (minor deviations accepted).",
        'Thresholds tuned on half A for topical F1; half B is held out. Untagged counts as "none".',
        "",
        "| Method | Thresholds | Half | Accuracy | Precision | Recall | F1 | Coverage |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for m in ("keyword", "raw", "centered"):
        th = "-" if m == "keyword" else f"sim ≥ {r[m]['min_sim']}, margin ≥ {r[m]['min_margin']}"
        for h in ("B", "all"):
            s = r[m][h]
            cells = " | ".join(f"{s[k]:.3f}" for k in ("accuracy", "precision", "recall", "f1", "coverage"))
            lines.append(f"| {m} | {th} | {h} | {cells} |")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", default="v1")
    run(ap.parse_args().name)
