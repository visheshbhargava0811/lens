"""Clustering eval (docs/04, docs/08): gold-set loader and metrics.

Gold format, one JSONL row per labeled article (data/evals/clustering/*.jsonl):

    {"id": "<article_id>",
     "inputs": {"article_id", "source", "language", "published_at", "title", "snippet"},
     "reference_outputs": {"story": "<gold story label>"},
     "tags": {"language", "cross_lingual", "developing", "hard_negative_group", "difficulty"},
     "annotator_ids": ["..."], "created_at": "..."}

Articles with the same `story` label report the same event. Stories that share a
`hard_negative_group` are the same topic but different events.
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from itertools import combinations
from pathlib import Path
from typing import Any

from sklearn.metrics import adjusted_rand_score, homogeneity_completeness_v_measure

from lens.core.settings import REPO_ROOT

GOLD_DIR = REPO_ROOT / "data/evals/clustering"


@dataclass(frozen=True)
class GoldArticle:
    article_id: str
    story: str
    language: str
    source: str
    published_at: str
    title: str
    snippet: str | None
    hard_negative_group: str | None


def load_gold(paths: Sequence[Path] | None = None) -> list[GoldArticle]:
    paths = list(paths) if paths is not None else sorted(GOLD_DIR.glob("gold_*.jsonl"))
    out: list[GoldArticle] = []
    seen: set[str] = set()
    for path in paths:
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if not line.strip():
                continue
            row = json.loads(line)
            inp, tags = row["inputs"], row.get("tags", {})
            story = str(row["reference_outputs"]["story"]).strip()
            if not story:
                raise ValueError(f"{path.name}:{n}: empty story label")
            if row["id"] in seen:
                raise ValueError(f"{path.name}:{n}: duplicate article {row['id']}")
            seen.add(row["id"])
            out.append(
                GoldArticle(
                    article_id=row["id"],
                    story=story,
                    language=inp["language"],
                    source=inp["source"],
                    published_at=inp["published_at"],
                    title=inp["title"],
                    snippet=inp.get("snippet"),
                    hard_negative_group=tags.get("hard_negative_group"),
                )
            )
    return out


# ------------------------------------------------------------------ metrics


def bcubed(gold: Sequence[str], pred: Sequence[str]) -> tuple[float, float, float]:
    """B-cubed precision, recall and F1 (Amigo et al. 2009), averaged over items."""
    if len(gold) != len(pred) or not gold:
        raise ValueError("gold and pred must be non-empty and the same length")
    by_gold: dict[str, set[int]] = defaultdict(set)
    by_pred: dict[str, set[int]] = defaultdict(set)
    for i, (g, p) in enumerate(zip(gold, pred, strict=True)):
        by_gold[g].add(i)
        by_pred[p].add(i)
    precision = recall = 0.0
    for g, p in zip(gold, pred, strict=True):
        overlap = len(by_gold[g] & by_pred[p])
        precision += overlap / len(by_pred[p])
        recall += overlap / len(by_gold[g])
    n = len(gold)
    precision, recall = precision / n, recall / n
    f1 = 0.0 if precision + recall == 0 else 2 * precision * recall / (precision + recall)
    return precision, recall, f1


def cross_lingual_pairs(gold: Sequence[str], pred: Sequence[str], langs: Sequence[str]) -> dict[str, float | int]:
    """Pairs of articles in different languages. Recall: share of same-event pairs put together.
    Precision: share of predicted-together pairs that really are the same event."""
    base = [lang.split("-")[0] for lang in langs]
    tp = fn = fp = 0
    for i, j in combinations(range(len(gold)), 2):
        if base[i] == base[j]:
            continue
        same_gold, same_pred = gold[i] == gold[j], pred[i] == pred[j]
        tp += same_gold and same_pred
        fn += same_gold and not same_pred
        fp += same_pred and not same_gold
    return {
        "pairs_gold": tp + fn,
        "recall": tp / (tp + fn) if tp + fn else float("nan"),
        "precision": tp / (tp + fp) if tp + fp else float("nan"),
    }


def merge_error_rate(gold: Sequence[str], pred: Sequence[str]) -> float:
    """Share of predicted multi-article clusters that mix two or more gold stories."""
    members: dict[str, set[str]] = defaultdict(set)
    sizes: Counter[str] = Counter(pred)
    for g, p in zip(gold, pred, strict=True):
        members[p].add(g)
    multi = [p for p, n in sizes.items() if n > 1]
    return sum(1 for p in multi if len(members[p]) > 1) / len(multi) if multi else 0.0


def hard_negative_merges(gold: Sequence[GoldArticle], pred: Sequence[str]) -> int:
    """Predicted clusters that join different stories from the same hard-negative group."""
    groups: dict[str, set[str]] = defaultdict(set)
    for a, p in zip(gold, pred, strict=True):
        if a.hard_negative_group:
            groups[p].add(f"{a.hard_negative_group}|{a.story}")
    count = 0
    for stories in groups.values():
        by_group: dict[str, set[str]] = defaultdict(set)
        for key in stories:
            grp, story = key.split("|", 1)
            by_group[grp].add(story)
        count += sum(1 for s in by_group.values() if len(s) > 1)
    return count


def score(gold: Sequence[GoldArticle], pred: Sequence[str], verifier_calls: int = 0) -> dict[str, Any]:
    labels = [a.story for a in gold]
    p, r, f1 = bcubed(labels, pred)
    h, c, v = homogeneity_completeness_v_measure(labels, pred)
    return {
        "articles": len(gold),
        "gold_stories": len(set(labels)),
        "pred_clusters": len(set(pred)),
        "bcubed_precision": round(p, 4),
        "bcubed_recall": round(r, 4),
        "bcubed_f1": round(f1, 4),
        "ari": round(float(adjusted_rand_score(labels, pred)), 4),
        "v_measure": round(float(v), 4),
        "homogeneity": round(float(h), 4),
        "completeness": round(float(c), 4),
        "cross_lingual": {
            k: (round(x, 4) if isinstance(x, float) else x)
            for k, x in cross_lingual_pairs(labels, pred, [a.language for a in gold]).items()
        },
        "merge_error_rate": round(merge_error_rate(labels, pred), 4),
        "hard_negative_merges": hard_negative_merges(gold, pred),
        "verifier_call_rate": round(verifier_calls / len(gold), 4),
    }
