import csv
import json
from collections.abc import Sequence
from pathlib import Path

import pytest

from lens.evals import clustering_labeling as lab
from lens.evals.clustering import load_gold

ROWS = [
    # draft, story, hn, lang, source, time, title
    ("d1", "pune-metro", "", "en", "A", "2026-09-21 08:00", "Pune metro budget approved"),
    ("d1", "pune-metro", "", "mr", "B", "2026-09-21 16:30", "पुणे मेट्रोला निधी मंजूर"),
    ("d1", "pune-metro", "", "hi", "C", "2026-09-21 18:00", "पुणे मेट्रो का बजट मंजूर"),
    ("d2", "flood-assam", "hn-floods", "en", "A", "2026-09-21 09:00", "Floods in Assam"),
    ("d3", "flood-kerala", "hn-floods", "en", "B", "2026-09-21 09:30", "Floods in Kerala"),
    ("s9", "drop", "", "hi", "C", "2026-09-21 10:00", "आज का राशिफल"),
]


def _csv(path: Path, rows: Sequence[tuple[str, ...]]) -> Path:
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(lab.COLUMNS)
        for n, (draft, story, hn, lang, src, t, title) in enumerate(rows, 1):
            w.writerow([n, draft, story, hn, "", lang, src, t, title, "", f"id-{n}"])
    return path


def test_import_builds_gold_with_tags(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(lab, "GOLD_DIR", tmp_path)
    out = lab.import_labels(_csv(tmp_path / "in.csv", ROWS), "tester", "t1")
    rows = [json.loads(line) for line in out.read_text().splitlines()]
    assert len(rows) == 5  # "drop" excluded
    metro = [r for r in rows if r["reference_outputs"]["story"] == "pune-metro"]
    assert all(r["tags"]["cross_lingual"] and r["tags"]["developing"] for r in metro)
    assert metro[0]["inputs"]["published_at"] == "2026-09-21T02:30:00+00:00"  # IST -> UTC
    gold = load_gold([out])
    assert {g.hard_negative_group for g in gold if g.story.startswith("flood")} == {"hn-floods"}


def test_import_rejects_empty_labels(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(lab, "GOLD_DIR", tmp_path)
    bad = [("d1", "", "", "en", "A", "2026-09-21 08:00", "x")]
    with pytest.raises(SystemExit, match="empty story"):
        lab.import_labels(_csv(tmp_path / "bad.csv", bad), "tester", "t2")
