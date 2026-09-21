"""Language-ID eval (Phase 1A acceptance). Usage: uv run python -m lens.evals.langid [--heldout] [--write]"""

from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from datetime import UTC, datetime

from lens.core.settings import REPO_ROOT
from lens.ingest.triage import detect_language

DATASETS = {
    "dev": REPO_ROOT / "data/evals/langid/sample_v1.jsonl",  # rules were tuned on this set
    "heldout": REPO_ROOT / "data/evals/langid/heldout_v1.jsonl",  # never used for tuning
}


def evaluate(split: str = "dev") -> dict[str, object]:
    path = DATASETS[split]
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    per: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    confusion: Counter[tuple[str, str]] = Counter()
    errors = []
    for r in rows:
        pred = detect_language(r["text"]).code
        per[r["label"]][1] += 1
        if pred == r["label"]:
            per[r["label"]][0] += 1
        else:
            confusion[(r["label"], pred)] += 1
            errors.append({"id": r["id"], "label": r["label"], "pred": pred, "text": r["text"]})
    correct = sum(c for c, _ in per.values())
    return {
        "n": len(rows),
        "accuracy": round(correct / len(rows), 4),
        "per_label": {
            k: {"correct": c, "n": n, "accuracy": round(c / n, 4)} for k, (c, n) in sorted(per.items())
        },
        "confusion": {f"{a}->{b}": n for (a, b), n in confusion.most_common()},
        "errors": errors,
    }


def main(argv: list[str]) -> int:
    split = "heldout" if "--heldout" in argv else "dev"
    result = evaluate(split)
    print(json.dumps({k: v for k, v in result.items() if k != "errors"}, ensure_ascii=False, indent=2))
    for e in result["errors"]:  # type: ignore[attr-defined]
        print(f"  {e['id']}: {e['label']} -> {e['pred']}  {e['text'][:70]}")
    if "--write" in argv:
        out = REPO_ROOT / "reports" / f"langid_{split}_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}.json"
        out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"wrote {out.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
