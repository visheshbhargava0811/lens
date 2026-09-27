"""Mirror data/evals/<suite>/*.jsonl as LangSmith datasets (docs/08), named `lens-<suite>-<file stem>`.

Idempotent: each example id is derived from the row id, so re-running adds new rows, updates changed
ones and leaves the rest. The files stay the source of truth; LangSmith is the browsable copy that
experiments and the annotation queue attach to. Eval files hold no user data (synthetic questions,
public headlines); rows promoted from real traffic are PII-masked before they are written
(`lens.ops.annotation`).

    python -m lens.ops.datasets            # sync everything
"""

from __future__ import annotations

import hashlib
import json
import sys
import uuid
from pathlib import Path
from typing import Any, Protocol

from lens.core.settings import REPO_ROOT

EVALS = REPO_ROOT / "data" / "evals"
# Older files that predate the docs/08 row format: mapped, not rewritten.
LEGACY = {"langid": lambda r: ({"text": r["text"]}, {"label": r["label"]}, {"origin": r["origin"]})}


class Client(Protocol):
    def has_dataset(self, *, dataset_name: str) -> bool: ...
    def create_dataset(self, dataset_name: str, *, description: str) -> Any: ...
    def read_dataset(self, *, dataset_name: str) -> Any: ...
    def list_examples(self, *, dataset_id: Any) -> Any: ...
    def create_examples(self, *, dataset_id: Any, examples: list[dict[str, Any]]) -> Any: ...
    def update_examples(self, *, dataset_id: Any, updates: list[dict[str, Any]]) -> Any: ...


def example(suite: str, stem: str, row: dict[str, Any]) -> dict[str, Any]:
    if "inputs" in row:
        inputs, outputs = row["inputs"], row.get("reference_outputs", {})
        meta = {
            "tags": row.get("tags", {}),
            "annotator_ids": row.get("annotator_ids", []),
            "created_at": row.get("created_at"),
        }
    else:
        inputs, outputs, meta = LEGACY[suite](row)
    return {
        "id": str(uuid.uuid5(uuid.NAMESPACE_URL, f"lens/{suite}/{stem}/{row['id']}")),
        "inputs": inputs,
        "outputs": outputs,
        "metadata": {"row_id": row["id"], **meta},
    }


def _digest(ex: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps([ex["inputs"], ex["outputs"], ex["metadata"]], sort_keys=True).encode()
    ).hexdigest()


def sync_file(client: Client, path: Path) -> dict[str, int]:
    suite = path.parent.name
    if suite not in LEGACY:
        first = json.loads(path.read_text(encoding="utf-8").splitlines()[0])
        if "inputs" not in first:
            return {"skipped": 1}
    name = f"lens-{suite}-{path.stem}"
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    wanted = {e["id"]: e for e in (example(suite, path.stem, r) for r in rows)}
    if not client.has_dataset(dataset_name=name):
        client.create_dataset(name, description=f"Mirror of {path.relative_to(REPO_ROOT)} (docs/08)")
    ds = client.read_dataset(dataset_name=name)
    have = {
        str(e.id): _digest(
            {
                "inputs": e.inputs,
                "outputs": e.outputs or {},
                "metadata": {k: v for k, v in (e.metadata or {}).items() if k != "dataset_split"},
            }
        )
        for e in client.list_examples(dataset_id=ds.id)
    }
    new = [e for i, e in wanted.items() if i not in have]
    changed = [e for i, e in wanted.items() if i in have and have[i] != _digest(e)]
    if new:
        client.create_examples(dataset_id=ds.id, examples=new)
    if changed:
        client.update_examples(dataset_id=ds.id, updates=changed)
    return {"created": len(new), "updated": len(changed), "unchanged": len(wanted) - len(new) - len(changed)}


def main() -> int:
    from langsmith import Client as LangSmith

    from lens.core.settings import get_settings
    from lens.core.tracing import configure_tracing

    configure_tracing(get_settings())  # exports the LangSmith key from .env
    client = LangSmith()
    for path in sorted(EVALS.glob("*/*.jsonl")):
        print(f"{path.relative_to(REPO_ROOT)}: {sync_file(client, path)}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
