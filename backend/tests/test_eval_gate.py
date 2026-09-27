"""docs/08: a deliberately broken prompt must fail the CI gate."""

import json
import shutil
from pathlib import Path
from typing import Any

import pytest

from lens.core.settings import REPO_ROOT
from lens.ops import fingerprint as fp
from lens.ops.gate import check

GATES: dict[str, dict[str, Any]] = {
    "adversarial_pass_rate": {"suite": "ask", "min": 0.95},
    "retrieval_recall_at_10": {"suite": "retrieval", "min_delta_vs_baseline": -0.02},
    "faithfulness_judge": {"suite": "golden_answers", "min": 0.95, "pending": "no dataset"},
}
QU = f"{fp.SKILLS}/query_understanding.md"


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A copy of just the files the ask and retrieval suites fingerprint."""
    for dep in {d.partition(":")[0] for s in ("ask", "retrieval") for d in fp.DEPS[s]}:
        (tmp_path / dep).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(REPO_ROOT / dep, tmp_path / dep)
    monkeypatch.setattr(fp, "REPO_ROOT", tmp_path)
    return tmp_path


def _reports(adv: float = 1.0, recall: float = 0.97) -> dict[str, dict[str, Any]]:
    return {
        "ask": {"fingerprint": fp.fingerprint("ask"), "metrics": {"adversarial_pass_rate": adv}},
        "retrieval": {"fingerprint": fp.fingerprint("retrieval"), "metrics": {"retrieval_recall_at_10": recall}},
    }


def _status(checks: list[Any]) -> dict[str, str]:
    return {c.gate: c.status for c in checks}


def test_fresh_passing_reports_pass(repo: Path) -> None:
    got = _status(check(GATES, _reports(), {"retrieval_recall_at_10": 0.97}))
    assert got == {"adversarial_pass_rate": "pass", "retrieval_recall_at_10": "pass", "faithfulness_judge": "pending"}


def test_broken_prompt_fails_the_gate(repo: Path) -> None:
    reports = _reports()  # measured on the good prompt
    prompt = repo / QU
    prompt.write_text(prompt.read_text().replace("removed_premises", "ignored_field"))  # degrade it
    checks = check(GATES, reports, {"retrieval_recall_at_10": 0.97})
    assert _status(checks)["adversarial_pass_rate"] == "fail"
    assert "stale" in next(c.detail for c in checks if c.gate == "adversarial_pass_rate")
    assert _status(checks)["retrieval_recall_at_10"] == "pass"  # retrieval does not use that prompt


def test_rerun_on_a_broken_prompt_still_fails_on_the_metric(repo: Path) -> None:
    got = _status(check(GATES, _reports(adv=0.80), {"retrieval_recall_at_10": 0.97}))
    assert got["adversarial_pass_rate"] == "fail"


def test_delta_gate_needs_a_baseline_and_catches_regressions(repo: Path) -> None:
    assert _status(check(GATES, _reports(recall=0.97), {}))["retrieval_recall_at_10"] == "fail"
    assert (
        _status(check(GATES, _reports(recall=0.94), {"retrieval_recall_at_10": 0.97}))["retrieval_recall_at_10"]
        == "fail"
    )


def test_missing_report_fails(repo: Path) -> None:
    assert _status(check(GATES, {}, {}))["adversarial_pass_rate"] == "fail"


def test_committed_reports_pass_the_real_gate() -> None:
    """What CI runs: the committed reports/eval/*.json against config/eval_gates.yaml."""
    from lens.ops.gate import run

    failed = [c for c in run() if c.status == "fail"]
    assert not failed, json.dumps([c.__dict__ for c in failed], indent=1)
