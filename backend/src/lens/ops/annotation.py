"""Guard failures to a LangSmith annotation queue, and reviewed ones back into datasets (docs/08).

sweep: every guard run scored 0 (`guard.<id>` feedback from `traced_guard`) in the last
    `annotation.sweep_hours` is added to the `lens-guard-failures` queue, skipping runs already there.
    Polling rather than enqueueing inside the guard: traces upload asynchronously, so a run may not
    exist in LangSmith yet when the guard returns. The pipeline worker sweeps every pass.
promote: a reviewer marks a queued run with feedback `promote` = 1 and writes the expected behaviour
    in the comment. Those runs' root inputs (the Ask question), PII-masked, become rows in
    data/evals/promoted/promoted_v1.jsonl, mirrored to LangSmith by `lens.ops.datasets`, for triage
    into the scored suites.

    python -m lens.ops.annotation sweep|promote
"""

from __future__ import annotations

import asyncio
import json
import sys
from datetime import UTC, datetime, timedelta
from typing import Any

from langsmith import Client
from langsmith.schemas import RunKey

from lens.core.config_files import load_yaml
from lens.core.settings import REPO_ROOT, get_settings
from lens.core.tracing import configure_tracing
from lens.guardrails.pii import mask_any

QUEUE = "lens-guard-failures"
FAILED_GUARDS = 'and(has(tags, "guardrail"), eq(feedback_score, 0))'
PROMOTED = REPO_ROOT / "data" / "evals" / "promoted" / "promoted_v1.jsonl"
RUBRIC = (
    "A guard failed on this run. Was the guard right? If the case shows a real problem worth keeping "
    "(a missed premise, an injection, a wrong refusal), add feedback `promote` = 1 and write the "
    "expected behaviour in the comment."
)


def client() -> Client:
    configure_tracing(get_settings())  # exports the key from .env
    return Client()


def queue_id(c: Client) -> str:
    found = list(c.list_annotation_queues(name=QUEUE))
    q = found[0] if found else c.create_annotation_queue(name=QUEUE, rubric_instructions=RUBRIC)
    return str(q.id)


async def _failed_guard_runs(c: Client, project_id: str, since: datetime) -> list[RunKey]:
    # The query API returns only `id` unless fields are selected; RunKey needs the start time.
    runs = c.runs.query(
        project_ids=[project_id], min_start_time=since, filter=FAILED_GUARDS, selects=["ID", "START_TIME"]
    )
    return [
        RunKey(run_id=str(r.id), session_id=project_id, start_time=r.start_time) async for r in runs if r.start_time
    ]


def sweep(c: Client | None = None, now: datetime | None = None) -> dict[str, int]:
    c = c or client()
    since = (now or datetime.now(UTC)) - timedelta(hours=load_yaml("eval_gates.yaml")["annotation"]["sweep_hours"])
    project = c.read_project(project_name=get_settings().langsmith_project)
    failed = asyncio.run(_failed_guard_runs(c, str(project.id), since))
    qid = queue_id(c)
    queued = {str(r.id) for r in c.list_runs_from_annotation_queue(qid)}
    new = [r for r in failed if str(r["run_id"]) not in queued]
    if new:
        c.add_runs_to_annotation_queue(qid, runs=new)
    return {"failed_guard_runs": len(failed), "queued": len(new)}


def promote(c: Client | None = None) -> dict[str, int]:
    c = c or client()
    have = {json.loads(line)["id"] for line in PROMOTED.read_text().splitlines()} if PROMOTED.exists() else set()
    rows: list[dict[str, Any]] = []
    queued = {str(r.id): r for r in c.list_runs_from_annotation_queue(queue_id(c))}
    marked = {  # the reviewer's promote = 1 is the decision; one call for the whole queue
        str(f.run_id): f
        for f in c.list_feedback(run_ids=list(queued), feedback_key=["promote"])
        if f.score == 1 and f.run_id is not None
    }
    for run_id, fb in marked.items():
        rid = f"promoted-{run_id}"
        if rid in have:
            continue
        run = queued[run_id]
        root = c.read_run(c.read_run(run_id).trace_id)
        guard = (run.extra or {}).get("metadata", {}).get("guard", run.name)
        rows.append(
            {
                "id": rid,
                "inputs": mask_any(root.inputs or {}),  # G-OUT-05: real questions are masked before storage
                "reference_outputs": {"expected": mask_any(fb.comment or "")},
                "tags": {"source": "annotation_queue", "guard": guard, "graph": root.name},
                "annotator_ids": ["langsmith-reviewer"],
                "created_at": datetime.now(UTC).isoformat(),
            }
        )
    if rows:
        PROMOTED.parent.mkdir(parents=True, exist_ok=True)
        with PROMOTED.open("a", encoding="utf-8") as f:
            f.writelines(json.dumps(r, ensure_ascii=False) + "\n" for r in rows)
    return {"promoted": len(rows)}


if __name__ == "__main__":
    print({"sweep": sweep, "promote": promote}[sys.argv[1]]())
