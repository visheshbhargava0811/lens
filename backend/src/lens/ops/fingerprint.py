"""What each eval suite measured (docs/08 release process): a hash of the prompts, config keys and
datasets that decide its result. A report is valid only for the fingerprint it records, so changing a
prompt or a threshold without re-running its suite fails the gate (`lens.ops.gate`).

A dependency is a repo path, or `file.yaml:key.subkey` for one part of a config file (so an Ask tier
change does not invalidate the clustering report). Source code is deliberately not hashed: unit tests
cover it, and hashing it would force a live re-eval for every refactor (ADR-0039).
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

import yaml

from lens.core.settings import REPO_ROOT

SKILLS = "backend/src/lens/agents/skills"
ASK_TIERS = ("query_understanding", "ask_synthesis", "ask_judge", "translation")

DEPS: dict[str, list[str]] = {
    "langid": ["data/evals/langid/heldout_v1.jsonl"],
    "stored_outputs": [],  # deterministic check over stored claims; always re-run
    "topics": [
        "config/clustering.yaml:topics",
        "config/models.yaml:tiers.embedding",
        "data/topics/prototypes.npz",
        "data/evals/topics/gold_v1.jsonl",
    ],
    "clustering": [
        *(
            f"config/clustering.yaml:{k}"
            for k in (
                "window_hours",
                "candidates",
                "weights",
                "time_decay_hours",
                "thresholds",
                "borderline_without_verifier",
                "story_centroid_update",
            )
        ),
        "config/models.yaml:tiers.embedding",
        "data/evals/clustering/gold_v1.jsonl",
    ],
    "retrieval": [
        "config/retrieval.yaml:tier1",
        "config/models.yaml:tiers.embedding",
        "data/evals/retrieval/queries_v1.jsonl",
    ],
    "ask": [
        *(
            f"{SKILLS}/{s}.md"
            for s in (
                "query_understanding",
                "query_followups",
                "ask_synthesis",
                "evidence_rules",
                "judge_faithfulness",
                "translation",
                "translation_check",
                "factcheck_match",
            )
        ),
        "config/factchecks.yaml:match",
        "config/factchecks.yaml:ask",
        *(f"config/models.yaml:tiers.{t}" for t in (*ASK_TIERS, "embedding", "analysis")),
        *(f"config/models.yaml:fallbacks.{t}" for t in ASK_TIERS),
        "config/models.yaml:max_wait_s",
        "config/retrieval.yaml",
        "config/guardrails.yaml",
        "data/evals/adversarial/adversarial_v1.jsonl",
        "data/evals/adversarial/benign_v1.jsonl",
    ],
    "factcheck": [
        f"{SKILLS}/factcheck_match.md",
        "config/models.yaml:tiers.analysis",
        "config/models.yaml:fallbacks.analysis",
        "config/factchecks.yaml:match",
        "data/evals/factcheck_match/gold_v1.jsonl",
    ],
    "judge": [
        f"{SKILLS}/judge_faithfulness.md",
        "config/models.yaml:tiers.judge",
        "data/evals/judge_calibration/gold_v2.jsonl",
    ],
}


def _part(dep: str) -> bytes:
    path, _, key = dep.partition(":")
    raw = (REPO_ROOT / path).read_bytes()
    if not key:
        return raw
    node: Any = yaml.safe_load(raw)
    for k in key.split("."):
        node = node.get(k) if isinstance(node, dict) else None
    return json.dumps(node, sort_keys=True, ensure_ascii=False).encode()


def fingerprint(suite: str) -> str:
    h = hashlib.sha256()
    for dep in sorted(DEPS[suite]):
        h.update(dep.encode() + b"\0" + hashlib.sha256(_part(dep)).digest())
    return h.hexdigest()[:16]
