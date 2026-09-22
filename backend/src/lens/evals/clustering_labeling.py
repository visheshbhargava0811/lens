"""Labeling export and import for the clustering gold set (docs/04, docs/08).

Export: `make cluster-label-export` writes data/evals/clustering/to_label_<date>.csv. Articles come
from a recent window and are pre-grouped by a draft clustering (average-linkage on BGE-M3 article
vectors), so labeling is mostly correcting. Humans edit the `story` column; see LABELING.md.

Import: `make cluster-label-import FILE=... ANNOTATOR=...` validates the CSV and writes
data/evals/clustering/gold_<name>.jsonl in the docs/08 format.
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import sys
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
from sklearn.cluster import AgglomerativeClustering
from sqlalchemy import select
from sqlalchemy.orm import Session

from lens.core.settings import REPO_ROOT
from lens.db.models import Article, Source
from lens.db.session import get_engine
from lens.evals.clustering import GOLD_DIR
from lens.retrieval.qdrant_store import fetch_article_vectors, get_qdrant

IST = ZoneInfo("Asia/Kolkata")


def _show(path: Path) -> str:
    return str(path.relative_to(REPO_ROOT)) if path.is_relative_to(REPO_ROOT) else str(path)


COLUMNS = [
    "row",
    "draft_group",
    "story",
    "hard_negative_group",
    "notes",
    "language",
    "source",
    "published_at_ist",
    "title",
    "snippet",
    "article_id",
]


def _draft_groups(vectors: np.ndarray, distance: float) -> np.ndarray:
    model = AgglomerativeClustering(n_clusters=None, metric="cosine", linkage="average", distance_threshold=distance)
    labels: np.ndarray = model.fit_predict(vectors)
    return labels


def export(hours: int, target_stories: int, distance: float, singletons: int, seed: int) -> Path:
    now = datetime.now(UTC)
    with Session(get_engine()) as session:
        rows = session.execute(
            select(Article, Source.name)
            .join(Source, Source.id == Article.source_id)
            # Syndicated copies are trivially the same story as their original: leave them out.
            .where(
                Article.is_news,
                Article.original_article_id.is_(None),
                Article.published_at >= now - timedelta(hours=hours),
            )
            .order_by(Article.published_at)
        ).all()
    arts = [(r[0], r[1]) for r in rows]
    vecs = fetch_article_vectors(get_qdrant(), [str(a.id) for a, _ in arts])
    arts = [(a, s) for a, s in arts if str(a.id) in vecs]
    if len(arts) < 10:
        raise SystemExit(f"only {len(arts)} indexed articles in the last {hours} h; run `make index` first")
    mat = np.stack([vecs[str(a.id)] for a, _ in arts])
    labels = _draft_groups(mat, distance)

    groups: dict[int, list[int]] = defaultdict(list)
    for i, g in enumerate(labels):
        groups[int(g)].append(i)
    multi = {g: m for g, m in groups.items() if len({arts[i][1] for i in m}) >= 2}

    def base_lang(i: int) -> str:
        return str(arts[i][0].language).split("-")[0]

    cross = [g for g, m in multi.items() if len({base_lang(i) for i in m}) >= 2]
    same = [g for g in multi if g not in set(cross)]
    rng = random.Random(seed)
    rng.shuffle(cross)
    rng.shuffle(same)
    # Cross-lingual groups first (docs/04 wants 30+), then others, up to the target.
    chosen = (cross + same)[:target_stories]

    # Hard-negative hints: pairs of chosen groups whose centroids are close but not merged.
    cents = {g: mat[groups[g]].mean(axis=0) for g in chosen}
    for g in cents:
        cents[g] /= np.linalg.norm(cents[g])
    hn_of: dict[int, str] = {}
    hn_n = 0
    for gi, g in enumerate(chosen):
        for h in chosen[gi + 1 :]:
            sim = float(cents[g] @ cents[h])
            if 0.6 <= sim < 1 - distance and g not in hn_of and h not in hn_of:
                hn_n += 1
                hn_of[g] = hn_of[h] = f"hn-{hn_n:03d}"

    single_pool = [m[0] for m in groups.values() if len(m) == 1]
    rng.shuffle(single_pool)
    single_rows = single_pool[:singletons]

    out_rows = []
    for g in chosen:
        for i in sorted(groups[g], key=lambda i: arts[i][0].published_at):
            out_rows.append((f"d{g:04d}", hn_of.get(g, ""), i))
    for i in single_rows:
        out_rows.append((f"s{i:05d}", "", i))

    GOLD_DIR.mkdir(parents=True, exist_ok=True)
    path = GOLD_DIR / f"to_label_{now.strftime('%Y%m%d')}.csv"
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(COLUMNS)
        for n, (draft, hn, i) in enumerate(out_rows, start=1):
            a, source = arts[i]
            w.writerow(
                [
                    n,
                    draft,
                    draft,
                    hn,
                    "",
                    a.language,
                    source,
                    a.published_at.astimezone(IST).strftime("%Y-%m-%d %H:%M"),
                    a.title,
                    (a.snippet or "")[:300],
                    str(a.id),
                ]
            )
    print(
        f"wrote {_show(path)}: {len(out_rows)} articles, {len(chosen)} draft stories "
        f"({len([g for g in chosen if g in set(cross)])} cross-lingual), {hn_n} hard-negative hints, "
        f"{len(single_rows)} single-article distractors"
    )
    return path


def import_labels(csv_path: Path, annotator: str, name: str) -> Path:
    rows = list(csv.DictReader(csv_path.open(encoding="utf-8")))
    missing = [
        c for c in ("story", "article_id", "language", "source", "published_at_ist", "title") if c not in rows[0]
    ]
    if missing:
        raise SystemExit(f"CSV is missing columns: {missing}")
    stories: dict[str, list[dict[str, str]]] = defaultdict(list)
    for r in rows:
        story = r["story"].strip()
        if not story:
            raise SystemExit(f"row {r.get('row')}: empty story label")
        if story.lower() in ("drop", "skip", "not news"):
            continue  # labeler excluded this article
        stories[story].append(r)
    now = datetime.now(UTC).isoformat()
    out = GOLD_DIR / f"gold_{name}.jsonl"
    with out.open("w", encoding="utf-8") as f:
        for story, members in stories.items():
            langs = {m["language"].split("-")[0] for m in members}
            times = sorted(datetime.strptime(m["published_at_ist"], "%Y-%m-%d %H:%M") for m in members)
            developing = len(members) >= 3 and (times[-1] - times[0]) >= timedelta(hours=6)
            hn = next(
                (m["hard_negative_group"].strip() for m in members if m.get("hard_negative_group", "").strip()),
                None,
            )
            for m in members:
                published = datetime.strptime(m["published_at_ist"], "%Y-%m-%d %H:%M").replace(tzinfo=IST)
                f.write(
                    json.dumps(
                        {
                            "id": m["article_id"],
                            "inputs": {
                                "article_id": m["article_id"],
                                "source": m["source"],
                                "language": m["language"],
                                "published_at": published.astimezone(UTC).isoformat(),
                                "title": m["title"],
                                "snippet": m.get("snippet") or None,
                            },
                            "reference_outputs": {"story": story},
                            "tags": {
                                "language": m["language"],
                                "cross_lingual": len(langs) >= 2,
                                "developing": developing,
                                "hard_negative_group": hn,
                                "difficulty": (m.get("notes") or "").strip() or None,
                            },
                            "annotator_ids": [annotator],
                            "created_at": now,
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )
    n_cross = sum(1 for ms in stories.values() if len({m["language"].split("-")[0] for m in ms}) >= 2)
    n_hn = len(
        {next((m["hard_negative_group"] for m in ms if m.get("hard_negative_group")), "") for ms in stories.values()}
        - {""}
    )
    print(
        f"wrote {_show(out)}: {sum(len(v) for v in stories.values())} articles, "
        f"{len(stories)} stories ({n_cross} cross-lingual, {n_hn} hard-negative groups)"
    )
    return out


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("export")
    e.add_argument("--hours", type=int, default=48)
    e.add_argument("--stories", type=int, default=150)
    e.add_argument("--distance", type=float, default=0.25, help="cosine distance for draft groups")
    e.add_argument("--singletons", type=int, default=60)
    e.add_argument("--seed", type=int, default=7)
    i = sub.add_parser("import")
    i.add_argument("file", type=Path)
    i.add_argument("--annotator", required=True)
    i.add_argument("--name", required=True)
    a = ap.parse_args(argv)
    if a.cmd == "export":
        export(a.hours, a.stories, a.distance, a.singletons, a.seed)
    else:
        import_labels(a.file, a.annotator, a.name)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
