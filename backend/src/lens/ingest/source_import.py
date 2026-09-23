"""Import outlet ownership and ratings from a CSV (Phase 3; CLI and admin endpoint share this).

Rule 7: every row carries provenance. Rows are validated with the same models as the seed
registry (evidence_url for ownership, method_url for ratings, retrieved_at, confidence). The
whole file is rejected if any row is invalid, so a partial import can never happen.
Re-importing the same row is a no-op.

CSV columns: kind (ownership|rating), source_slug, then the fields of OwnershipEntry or
RatingEntry. Empty cells are treated as missing. `outlet_name_for_reference` is ignored, and a
row with nothing filled in beyond kind and source_slug is skipped (template:
data/sources/source_meta.template.csv).

Usage: uv run python -m lens.ingest.source_import path/to/file.csv
"""

from __future__ import annotations

import csv
import io
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from lens.db.models import Source, SourceOwnership, SourceRating
from lens.db.session import get_engine
from lens.ingest.registry import OwnershipEntry, RatingEntry


class ImportRejected(ValueError):
    def __init__(self, errors: list[str]) -> None:
        super().__init__("; ".join(errors))
        self.errors = errors


@dataclass
class ImportResult:
    ownership_added: int = 0
    ratings_added: int = 0
    unchanged: int = 0


def _parse(text: str, slugs: dict[str, Any]) -> list[tuple[str, Any, OwnershipEntry | RatingEntry]]:
    rows = list(csv.DictReader(io.StringIO(text)))
    errors: list[str] = []
    parsed: list[tuple[str, Any, OwnershipEntry | RatingEntry]] = []
    for n, raw in enumerate(rows, start=2):  # row 1 is the header
        row = {k.strip(): v.strip() for k, v in raw.items() if k and v is not None and v.strip() != ""}
        kind, slug = row.pop("kind", ""), row.pop("source_slug", "")
        row.pop("outlet_name_for_reference", None)  # template helper column
        if kind == "ownership" and row.get("dimension") == "ownership":
            row.pop("dimension")  # redundant on an ownership row
        if not row:
            continue  # a template row left blank: nothing to import
        if slug not in slugs:
            errors.append(f"row {n}: unknown source_slug {slug!r}")
            continue
        model: type[OwnershipEntry] | type[RatingEntry]
        if kind == "ownership":
            model = OwnershipEntry
        elif kind == "rating":
            model = RatingEntry
        else:
            errors.append(f"row {n}: kind must be 'ownership' or 'rating', got {kind!r}")
            continue
        try:
            parsed.append((kind, slugs[slug], model.model_validate(row)))
        except ValidationError as e:
            fields = ", ".join(f"{'.'.join(map(str, err['loc']))}: {err['msg']}" for err in e.errors())
            errors.append(f"row {n}: {fields}")
    if not parsed and not errors:
        errors.append("the file has no filled-in rows")
    if errors:
        raise ImportRejected(errors)
    return parsed


def import_csv(session: Session, text: str) -> ImportResult:
    slugs = {s.slug: s.id for s in session.execute(select(Source)).scalars()}
    result = ImportResult()
    for kind, source_id, entry in _parse(text, slugs):
        values = {"source_id": source_id, **entry.model_dump(mode="json")}
        values["retrieved_at"] = entry.retrieved_at
        table = SourceOwnership if kind == "ownership" else SourceRating
        exists = session.execute(
            select(table.id).where(*(getattr(table, k) == v for k, v in values.items() if v is not None)).limit(1)
        ).first()
        if exists:
            result.unchanged += 1
            continue
        session.add(table(**values))
        if kind == "ownership":
            result.ownership_added += 1
        else:
            result.ratings_added += 1
    session.flush()
    return result


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    text = Path(sys.argv[1]).read_text(encoding="utf-8")
    try:
        with Session(get_engine()) as session, session.begin():
            r = import_csv(session, text)
    except ImportRejected as e:
        print("rejected, nothing imported:\n  " + "\n  ".join(e.errors))
        return 1
    print(f"imported {r.ownership_added} ownership and {r.ratings_added} rating rows ({r.unchanged} already present)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
