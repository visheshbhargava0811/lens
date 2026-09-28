"""factcheck_match eval (docs/08, Phase 8): the LLM verifier on labeled claim/fact-check pairs.

Precision first (docs/12): the gated number is same_claim precision of the pipeline (similarity at or
above `match.min_similarity` and verdict same_claim); recall is reported. Writes
reports/factcheck_<name>.json via `make eval` (suite `factcheck`).
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any

from lens.core.config_files import load_yaml
from lens.core.settings import REPO_ROOT

GOLD = REPO_ROOT / "data" / "evals" / "factcheck_match" / "gold_v1.jsonl"


@dataclass(frozen=True)
class _Check:  # the two fields the verifier reads from a FactCheck row
    id: str
    claim_reviewed: str


def _pr(pred: list[bool], gold: list[bool]) -> tuple[float | None, float | None]:
    tp = sum(p and g for p, g in zip(pred, gold, strict=True))
    return (tp / sum(pred) if sum(pred) else None, tp / sum(gold) if sum(gold) else None)


def run(llm: Any, sleep: float = 2.0) -> dict[str, Any]:
    from lens.factchecks.match import verify

    rows = [json.loads(line) for line in GOLD.read_text(encoding="utf-8").splitlines() if line.strip()]
    thr = load_yaml("factchecks.yaml")["match"]["min_similarity"]
    preds: list[str] = []
    for r in rows:
        fc = _Check(r["inputs"]["fact_check_id"], r["inputs"]["fact_check"])
        verdicts, _ = verify(llm, r["inputs"]["claim"], [fc])  # type: ignore[list-item]
        preds.append(verdicts.get(fc.id, ("different", ""))[0])
        time.sleep(sleep)
    gold = [r["reference_outputs"]["verdict"] for r in rows]
    passes = [r["tags"]["similarity"] >= thr for r in rows]
    same_p, same_r = _pr([p == "same_claim" for p in preds], [g == "same_claim" for g in gold])
    pipe_p, pipe_r = _pr(
        [p == "same_claim" and ok for p, ok in zip(preds, passes, strict=True)], [g == "same_claim" for g in gold]
    )
    stored = [p in ("same_claim", "related") and ok for p, ok in zip(preds, passes, strict=True)]
    stored_p, _ = _pr(stored, [g in ("same_claim", "related") for g in gold])
    confusion: dict[str, int] = {}
    for g, p in zip(gold, preds, strict=True):
        confusion[f"{g}->{p}"] = confusion.get(f"{g}->{p}", 0) + 1
    return {
        "factcheck_same_claim_precision": pipe_p,
        "factcheck_same_claim_recall": pipe_r,
        "verifier_same_claim_precision": same_p,
        "verifier_same_claim_recall": same_r,
        "stored_match_precision": stored_p,
        "accuracy": sum(p == g for p, g in zip(preds, gold, strict=True)) / len(gold),
        "n": len(rows),
        "min_similarity": thr,
        "confusion": confusion,
        "errors": [{"id": r["id"], "gold": g, "pred": p} for r, g, p in zip(rows, gold, preds, strict=True) if g != p],
    }
