"""Judge-calibration labeling: import parses yes/no/blank, and kappa handles degenerate cases."""

import json
from pathlib import Path

import pytest

from lens.evals import analysis


def test_import_keeps_only_labeled_rows(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(analysis, "GOLD_DIR", tmp_path)
    monkeypatch.setattr(analysis, "REPO_ROOT", tmp_path)
    csv_path = tmp_path / "labeled.csv"
    csv_path.write_text(
        "row,supported,notes,sentence,evidence,languages,summary_id,section,article_ids\n"
        "1,Yes,,S1,E1,en,x,,a\n"
        "2,no,hard,S2,E2,\"en,hi\",x,,a\n"
        "3,,,S3,E3,hi,x,,a\n"
        "4,maybe,,S4,E4,hi,x,,a\n",
        encoding="utf-8",
    )
    out = analysis.import_labels(csv_path, annotator="vishesh", name="t")
    items = [json.loads(line) for line in out.read_text(encoding="utf-8").splitlines()]
    assert [i["reference_outputs"]["supported"] for i in items] == [True, False]
    assert items[1]["tags"] == {"languages": ["en", "hi"], "notes": "hard"}
    assert items[0]["annotator_ids"] == ["vishesh"]


def test_kappa_is_undefined_with_one_class_and_perfect_when_identical() -> None:
    assert analysis._kappa([True, True], [True, True]) is None
    assert analysis._kappa([True, False, True], [True, False, True]) == 1.0
    assert analysis._kappa([True], [False]) is None
