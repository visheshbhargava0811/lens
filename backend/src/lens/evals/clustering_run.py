"""Run the clustering eval: baseline, docs starting config, and a threshold sweep with a held-out half.

Usage: uv run --extra ml python -m lens.evals.clustering_run [--gold FILE ...] [--name baseline]
Writes reports/clustering_<name>.md and .json.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np

from lens.clustering.core import ArticleFeatures, IncrementalClusterer
from lens.core.config_files import load_yaml
from lens.core.settings import REPO_ROOT
from lens.evals.clustering import GoldArticle, load_gold, score
from lens.retrieval.qdrant_store import fetch_article_vectors, get_qdrant


def vectors_for(gold: list[GoldArticle]) -> dict[str, np.ndarray]:
    vecs = fetch_article_vectors(get_qdrant(), [g.article_id for g in gold])
    missing = [g for g in gold if g.article_id not in vecs]
    if missing:  # not indexed yet (or the gold set came from elsewhere): encode directly
        from lens.nlp.embed import article_text, get_embedder

        enc = get_embedder().encode([article_text(g.title, g.snippet) for g in missing], sparse=False)
        vecs.update({g.article_id: v for g, v in zip(missing, enc.dense, strict=True)})
    return vecs


def run(gold: list[GoldArticle], vecs: dict[str, np.ndarray], cfg: dict[str, Any]) -> dict[str, Any]:
    feats = [ArticleFeatures(g.article_id, vecs[g.article_id], datetime.fromisoformat(g.published_at)) for g in gold]
    counter = iter(range(10**9))
    outcomes = IncrementalClusterer(cfg, id_factory=lambda: f"c{next(counter)}").run(feats)
    pred_by_id = {o.article_id: o.story_id for o in outcomes}
    return score(gold, [pred_by_id[g.article_id] for g in gold], sum(o.verifier_called for o in outcomes))


def variant(base: dict[str, Any], **changes: Any) -> dict[str, Any]:
    cfg = copy.deepcopy(base)
    for key, value in changes.items():
        target = cfg
        *path, last = key.split(".")
        for p in path:
            target = target[p]
        target[last] = value
    return cfg


def split(gold: list[GoldArticle]) -> tuple[list[GoldArticle], list[GoldArticle]]:
    """Deterministic 50/50 split by story, so no story is in both halves."""

    def half(story: str) -> int:
        # A stable eval split, not a security use of SHA-1.
        digest = hashlib.sha1(story.encode(), usedforsecurity=False)  # nosemgrep
        return int(digest.hexdigest(), 16) % 2

    return [g for g in gold if half(g.story) == 0], [g for g in gold if half(g.story) == 1]


def sweep(
    tune: list[GoldArticle], vecs: dict[str, np.ndarray], base: dict[str, Any]
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    grid = []
    for time_w in (0.0, 0.1):
        for high in np.arange(0.60, 0.92, 0.02):
            for policy in ("new_story", "assign"):
                cfg = variant(
                    base,
                    **{
                        "weights.time": time_w,
                        "thresholds.high": round(float(high), 2),
                        "thresholds.low": round(float(high) - 0.10, 2),
                        "borderline_without_verifier": policy,
                    },
                )
                res = run(tune, vecs, cfg)
                grid.append(
                    {
                        "time_w": time_w,
                        "high": round(float(high), 2),
                        "policy": policy,
                        "bcubed_f1": res["bcubed_f1"],
                        "verifier_call_rate": res["verifier_call_rate"],
                    }
                )
    best = max(grid, key=lambda r: (r["bcubed_f1"], -r["verifier_call_rate"]))
    cfg = variant(
        base,
        **{
            "weights.time": best["time_w"],
            "thresholds.high": best["high"],
            "thresholds.low": round(best["high"] - 0.10, 2),
            "borderline_without_verifier": best["policy"],
        },
    )
    return cfg, grid


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--gold", type=Path, nargs="*")
    ap.add_argument("--name", default="baseline")
    a = ap.parse_args(argv)
    gold = load_gold(a.gold)
    if not gold:
        raise SystemExit("no gold set found in data/evals/clustering (gold_*.jsonl)")
    vecs = vectors_for(gold)
    base = load_yaml("clustering.yaml")

    dense_only = variant(base, **{"weights.time": 0.0, "weights.entity_jaccard": 0.0, "weights.event_type": 0.0})
    tune, test = split(gold)
    tuned_cfg, grid = sweep(tune, vecs, base)
    results = {
        "baseline_dense_only (docs thresholds)": {"all": run(gold, vecs, dense_only)},
        "docs_starting_config (dense + time)": {"all": run(gold, vecs, base)},
        "tuned_on_half_A": {
            "config": {
                "time_w": tuned_cfg["weights"]["time"],
                "thresholds": tuned_cfg["thresholds"],
                "borderline": tuned_cfg["borderline_without_verifier"],
            },
            "tune_half_A": run(tune, vecs, tuned_cfg),
            "heldout_half_B": run(test, vecs, tuned_cfg),
            "all": run(gold, vecs, tuned_cfg),
        },
    }
    stamp = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    out_json = REPO_ROOT / f"reports/clustering_{a.name}.json"
    out_json.write_text(
        json.dumps(
            {"generated": stamp, "gold": [str(p) for p in (a.gold or [])], "results": results, "sweep": grid},
            indent=2,
            ensure_ascii=False,
        )
        + "\n"
    )

    keys = [
        "bcubed_precision",
        "bcubed_recall",
        "bcubed_f1",
        "ari",
        "v_measure",
        "merge_error_rate",
        "hard_negative_merges",
        "verifier_call_rate",
    ]
    lines = [
        f"# Clustering eval: {a.name}",
        "",
        f"Generated {stamp}. Gold: {len(gold)} articles, "
        f"{len({g.story for g in gold})} stories. Raw numbers: `{out_json.relative_to(REPO_ROOT)}`.",
        "",
        "| Run | Split | " + " | ".join(keys) + " | cross-lingual recall | cross-lingual precision |",
        "|---|---|" + "---|" * (len(keys) + 2),
    ]
    for run_name, splits in results.items():
        for split_name, res in splits.items():
            if split_name == "config":
                continue
            cl = res["cross_lingual"]
            lines.append(
                f"| {run_name} | {split_name} | "
                + " | ".join(str(res[k]) for k in keys)
                + f" | {cl['recall']} | {cl['precision']} |"
            )
    lines += ["", f"Tuned config (chosen on half A only): `{results['tuned_on_half_A']['config']}`"]
    (REPO_ROOT / f"reports/clustering_{a.name}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
