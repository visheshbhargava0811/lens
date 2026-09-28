"""`make eval` (docs/08): runs every eval suite whose prompts/config/data changed since its last report,
writes reports/eval/<suite>.json (metrics + the fingerprint they were measured on) and
reports/eval_<date>.md with the gate table. Reuses each suite's own runner; nothing is re-implemented.

    python -m lens.evals.run_all                    # stale suites only (ask is live: LLM quota, ~40 min)
    python -m lens.evals.run_all --suites topics,langid --force
    python -m lens.evals.run_all --baseline         # promote current metrics to reports/eval/baseline.json
"""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from lens.core.config_files import load_yaml
from lens.core.settings import REPO_ROOT
from lens.ops.fingerprint import DEPS, fingerprint
from lens.ops.gate import EVAL_DIR, load_reports, render, run

REPORT_ONLY = {"judge"}  # live and not gated: run it by name


def langid() -> dict[str, Any]:
    from lens.evals.langid import evaluate

    r = evaluate("heldout")
    return {"langid_heldout_accuracy": r["accuracy"], "per_label": r["per_label"]}


def stored_outputs() -> dict[str, Any]:
    from lens.db.session import get_engine
    from lens.evals.analysis import quote_match

    with Session(get_engine()) as s:
        ok, n = quote_match(s)
    return {"quote_match_rate": ok / n if n else None, "stored_claims": n}


def topics() -> dict[str, Any]:
    from lens.evals.topics import GOLD, score
    from lens.nlp.topic_embed import _cfg, load_prototypes
    from lens.retrieval.qdrant_store import STORIES, fetch_article_vectors, get_qdrant

    gold = [json.loads(line) for line in GOLD.read_text(encoding="utf-8").splitlines() if line.strip()]
    protos, cfg = load_prototypes(), _cfg()
    assert protos is not None, "no topic prototypes: make topic-prototypes"
    vecs = fetch_article_vectors(get_qdrant(), [g["inputs"]["story_id"] for g in gold], STORIES)
    preds = [
        protos.assign(vecs[g["inputs"]["story_id"]], cfg["min_sim"], cfg["min_margin"])
        if g["inputs"]["story_id"] in vecs
        else None
        for g in gold
    ]
    s = score(preds, [g["reference_outputs"]["labels"] for g in gold])
    return {"topics_f1": s["f1"], **{f"topics_{k}": v for k, v in s.items() if k != "f1"}}


def clustering() -> dict[str, Any]:
    from lens.evals.clustering import load_gold
    from lens.evals.clustering_run import run as cluster_run
    from lens.evals.clustering_run import vectors_for

    gold = load_gold(None)
    r = cluster_run(gold, vectors_for(gold), load_yaml("clustering.yaml"))
    return {"clustering_bcubed_f1": r["bcubed_f1"], **{k: v for k, v in r.items() if k != "bcubed_f1"}}


def retrieval() -> dict[str, Any]:
    """Production tier 1 (dense over story centroids), evaluated as of each query's creation time: the
    window is anchored there and stories first seen later are dropped, so corpus growth is not drift."""
    from lens.db.models import Story
    from lens.db.session import get_engine
    from lens.evals.retrieval_run import story_metrics
    from lens.nlp.embed import get_embedder
    from lens.retrieval.qdrant_store import get_qdrant
    from lens.retrieval.search import encode_query, stories_dense

    path = REPO_ROOT / "data/evals/retrieval/queries_v1.jsonl"
    rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    rows = [r for r in rows if r["reference_outputs"]["relevant_story_ids"]]
    window = load_yaml("retrieval.yaml")["tier1"]["window_days"]
    client, embedder = get_qdrant(), get_embedder()
    recalls, mrrs = [], []
    with Session(get_engine()) as s:
        for r in rows:
            as_of = datetime.fromisoformat(r["created_at"])
            ranked = stories_dense(
                client, encode_query(embedder, r["inputs"]["query"], colbert=False), as_of, window, 50
            )
            ids = [sid for sid, _ in ranked]
            q = select(Story.id, Story.first_seen_at).where(Story.id.in_([uuid.UUID(i) for i in ids]))
            seen: dict[uuid.UUID, datetime] = {sid: t for sid, t in s.execute(q)}
            ranked_then = [i for i in ids if (t := seen.get(uuid.UUID(i))) is not None and t <= as_of][:10]
            m = story_metrics(ranked_then, set(r["reference_outputs"]["relevant_story_ids"]))
            recalls.append(m["recall@10"])
            mrrs.append(m["mrr@10"])
    return {
        "retrieval_recall_at_10": sum(recalls) / len(recalls),
        "retrieval_mrr_at_10": sum(mrrs) / len(mrrs),
        "n": len(rows),
    }


def ask() -> dict[str, Any]:
    from lens.evals.ask_adversarial import run_suite

    s = run_suite(f"eval_{fingerprint('ask')}")  # resumable: same fingerprint, same run
    return {
        "adversarial_pass_rate": s["adversarial_pass_rate"],
        "benign_false_block_rate": s["benign_false_block_rate"],
        "citation_presence": s["citation_presence"],
        "p95_ask_latency_s": (s["latency_s"] or {}).get("p95"),
        "p50_ask_latency_s": (s["latency_s"] or {}).get("p50"),
        "tokens_per_ask_mean": (s["tokens_per_ask"] or {}).get("mean"),
        "infra_failures": s["adversarial"]["infra_failures"] + s["benign"]["infra_failures"],
        "by_category": s["by_category"],
    }


def judge() -> dict[str, Any]:
    """Judge calibration against owner labels, per language (docs/08); report-only."""
    from lens.evals.analysis import run as analysis_run

    gold = REPO_ROOT / "data/evals/judge_calibration/gold_v2.jsonl"
    c = analysis_run(f"eval_judge_{fingerprint('judge')}", gold)["judge_calibration"]
    return {"judge_kappa": c["kappa"], "judge_agreement": c["agreement"], "by_language": c["by_language"]}


def factcheck() -> dict[str, Any]:
    from lens.evals.factcheck import run as fc_run
    from lens.llm.client import structured

    return fc_run(structured)


SUITES: dict[str, Callable[[], dict[str, Any]]] = {
    "langid": langid,
    "stored_outputs": stored_outputs,
    "topics": topics,
    "clustering": clustering,
    "retrieval": retrieval,
    "ask": ask,
    "factcheck": factcheck,
    "judge": judge,
}
assert set(SUITES) == set(DEPS)


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--suites", default=None, help="comma-separated; default: every stale gated suite")
    ap.add_argument("--force", action="store_true", help="re-run the chosen suites even if fresh")
    ap.add_argument("--baseline", action="store_true", help="promote current metrics to the baseline")
    a = ap.parse_args(argv)
    EVAL_DIR.mkdir(parents=True, exist_ok=True)
    reports = load_reports()

    if a.baseline:
        metrics = {k: v for r in reports.values() for k, v in r["metrics"].items() if isinstance(v, int | float)}
        (EVAL_DIR / "baseline.json").write_text(
            json.dumps(
                {
                    "set_at": datetime.now(UTC).isoformat(),
                    "fingerprints": {s: r["fingerprint"] for s, r in reports.items()},
                    "metrics": metrics,
                },
                indent=1,
            )
        )
        print(f"baseline set from {sorted(reports)}")
        return 0

    chosen = a.suites.split(",") if a.suites else [s for s in SUITES if s not in REPORT_ONLY]
    for suite in chosen:
        fp = fingerprint(suite)
        fresh = reports.get(suite, {}).get("fingerprint") == fp and DEPS[suite]
        if fresh and not a.force:
            print(f"{suite}: fresh ({fp}), skipped")
            continue
        print(f"{suite}: running ({fp})", flush=True)
        metrics = SUITES[suite]()
        rep = {"suite": suite, "fingerprint": fp, "generated_at": datetime.now(UTC).isoformat(), "metrics": metrics}
        (EVAL_DIR / f"{suite}.json").write_text(json.dumps(rep, indent=1, ensure_ascii=False, default=str))

    checks = run()
    out = REPO_ROOT / "reports" / f"eval_{datetime.now(UTC):%Y-%m-%d}.md"
    reports = load_reports()
    lines = [
        f"# Eval run {datetime.now(UTC):%Y-%m-%d %H:%M} UTC",
        "",
        render(checks),
        "",
        "## Suites",
        "",
        "| Suite | Fingerprint | Generated |",
        "|---|---|---|",
    ]
    lines += [f"| {s} | {r['fingerprint']} | {r['generated_at'][:16]} |" for s, r in sorted(reports.items())]
    out.write_text("\n".join(lines) + "\n")
    print(render(checks))
    print(f"\nwrote {out.relative_to(REPO_ROOT)}")
    return 1 if any(c.status == "fail" for c in checks) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
