"""Judge-calibration labeling: import parses yes/no/blank, and kappa handles degenerate cases."""

import json
from pathlib import Path

import pytest

from lens.evals import analysis


class _NoDB:
    """The import reads refs from the database; these rows have no summary_id, so it is never queried."""

    def __init__(self, *_: object) -> None: ...

    def __enter__(self) -> "_NoDB":
        return self

    def __exit__(self, *_: object) -> None: ...


def test_import_keeps_only_labeled_rows(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(analysis, "GOLD_DIR", tmp_path)
    monkeypatch.setattr(analysis, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(analysis, "get_engine", lambda: None)
    monkeypatch.setattr(analysis, "Session", _NoDB)
    csv_path = tmp_path / "labeled.csv"
    csv_path.write_text(
        "row,supported,notes,sentence,evidence,languages,summary_id,section,article_ids\n"
        "1,Yes,,S1,E1,en,,,\n"
        '2,no,hard,S2,E2,"en,hi",,,\n'
        "3,,,S3,E3,hi,,,\n"
        "4,maybe,,S4,E4,hi,,,\n",
        encoding="utf-8",
    )
    out = analysis.import_labels(csv_path, annotator="vishesh", name="t")
    items = [json.loads(line) for line in out.read_text(encoding="utf-8").splitlines()]
    assert [i["reference_outputs"]["supported"] for i in items] == [True, False]
    assert items[1]["tags"] == {"languages": ["en", "hi"], "notes": "hard"}
    assert items[0]["annotator_ids"] == ["vishesh"]
    assert items[0]["inputs"]["judge_evidence"] == "E1"  # falls back to the labeler's evidence


def test_kappa_is_undefined_with_one_class_and_perfect_when_identical() -> None:
    assert analysis._kappa([True, True], [True, True]) is None
    assert analysis._kappa([True, False, True], [True, False, True]) == 1.0
    assert analysis._kappa([True], [False]) is None


def test_fresh_export_excludes_sentences_already_in_any_gold_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(analysis, "GOLD_DIR", tmp_path)
    (tmp_path / "gold_v1.jsonl").write_text(
        json.dumps({"inputs": {"sentence": "Seen before."}}) + "\n", encoding="utf-8"
    )
    (tmp_path / "gold_v2.jsonl").write_text(json.dumps({"inputs": {"sentence": "Also seen."}}) + "\n", encoding="utf-8")
    assert analysis._labeled_sentences() == {"Seen before.", "Also seen."}


def test_run_resolves_a_relative_gold_path_before_calling_the_judge(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[Path] = []
    monkeypatch.setattr(analysis, "run", lambda name, gold: seen.append(gold))
    monkeypatch.setattr("sys.argv", ["x", "run", "--gold", "../data/evals/judge_calibration/gold_v3a.jsonl"])
    analysis.main()
    assert seen[0].is_absolute()
