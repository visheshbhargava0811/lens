"""CI eval gate (docs/08, ADR-0039). Offline and dependency-light so CI can run it without models or
keys: it checks the committed suite reports (reports/eval/<suite>.json) instead of re-running evals.

Fails when a gated suite's report is missing, when its fingerprint no longer matches the prompts and
config it measured (someone changed them without re-running `make eval`), or when a metric misses its
threshold or drops too far below reports/eval/baseline.json.

    python -m lens.ops.gate          # exit 1 on any failure
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from lens.core.settings import REPO_ROOT
from lens.ops.fingerprint import DEPS, fingerprint

EVAL_DIR = REPO_ROOT / "reports" / "eval"


@dataclass
class Check:
    gate: str
    status: str  # pass | fail | pending
    detail: str


def load_reports(eval_dir: Path = EVAL_DIR) -> dict[str, dict[str, Any]]:
    return {p.stem: json.loads(p.read_text()) for p in eval_dir.glob("*.json") if p.stem in DEPS}


def check(
    gates: dict[str, dict[str, Any]], reports: dict[str, dict[str, Any]], baseline: dict[str, float]
) -> list[Check]:
    out: list[Check] = []
    for gate, rule in gates.items():
        suite = rule["suite"]
        if "pending" in rule:
            out.append(Check(gate, "pending", rule["pending"]))
            continue
        rep = reports.get(suite)
        if rep is None:
            out.append(Check(gate, "fail", f"no {suite} report: run `make eval`"))
            continue
        if rep["fingerprint"] != fingerprint(suite):
            out.append(
                Check(gate, "fail", f"{suite} report is stale (its prompts/config/data changed): run `make eval`")
            )
            continue
        value = rep["metrics"].get(gate)
        if value is None:
            out.append(Check(gate, "fail", f"{suite} report has no {gate}"))
        elif "min" in rule:
            ok = value >= rule["min"]
            out.append(Check(gate, "pass" if ok else "fail", f"{value:.4g} (min {rule['min']})"))
        elif "max" in rule:
            ok = value <= rule["max"]
            out.append(Check(gate, "pass" if ok else "fail", f"{value:.4g} (max {rule['max']})"))
        else:
            base = baseline.get(gate)
            if base is None:
                out.append(Check(gate, "fail", "no baseline: run `make eval-baseline`"))
                continue
            delta = value - base
            ok = delta >= rule["min_delta_vs_baseline"]
            out.append(
                Check(gate, "pass" if ok else "fail", f"{value:.4g} vs baseline {base:.4g} (delta {delta:+.4f})")
            )
    return out


def run(eval_dir: Path = EVAL_DIR) -> list[Check]:
    gates = yaml.safe_load((REPO_ROOT / "config" / "eval_gates.yaml").read_text())["gates"]
    base_path = eval_dir / "baseline.json"
    baseline = json.loads(base_path.read_text())["metrics"] if base_path.exists() else {}
    return check(gates, load_reports(eval_dir), baseline)


def render(checks: list[Check]) -> str:
    mark = {"pass": "✅", "fail": "❌", "pending": "⏸"}
    rows = [f"| {c.gate} | {mark[c.status]} {c.status} | {c.detail} |" for c in checks]
    return "\n".join(["| Gate | Status | Detail |", "|---|---|---|", *rows])


def main() -> int:
    checks = run()
    print(render(checks))
    failed = [c for c in checks if c.status == "fail"]
    print(f"\n{len(failed)} gate(s) failed" if failed else "\nall measured gates pass")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
