"""Source metadata CSV import: provenance is required, bad files import nothing, re-import is a no-op."""

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from lens.db.models import Source, SourceOwnership, SourceRating
from lens.ingest.source_import import ImportRejected, import_csv

pytestmark = pytest.mark.db

HEADER = (
    "kind,source_slug,owner_name,parent_group,evidence_url,dimension,rater,value,method_url,retrieved_at,confidence\n"
)
OWN = "ownership,imp-a,Owner A,Group A,https://a.example/about,,,,,2026-09-20T00:00:00Z,high\n"
RATE = "rating,imp-a,,,,factuality,Example Rater,High,https://rater.example/method,2026-09-20T00:00:00Z,medium\n"


@pytest.fixture
def src(db: Session) -> Source:
    s = Source(slug="imp-a", name="A", homepage_url="https://a.example", language_codes=["en"], region="national")
    db.add(s)
    db.flush()
    return s


def _count(db: Session, table: type[SourceOwnership] | type[SourceRating]) -> int:
    return db.execute(select(func.count()).select_from(table)).scalar_one()


def test_import_and_reimport_is_idempotent(db: Session, src: Source) -> None:
    r = import_csv(db, HEADER + OWN + RATE)
    assert (r.ownership_added, r.ratings_added, r.unchanged) == (1, 1, 0)
    r = import_csv(db, HEADER + OWN + RATE)
    assert (r.ownership_added, r.ratings_added, r.unchanged) == (0, 0, 2)
    assert _count(db, SourceOwnership) == 1 and _count(db, SourceRating) == 1


@pytest.mark.parametrize(
    ("row", "problem"),
    [
        ("ownership,imp-a,Owner A,,,,,,,2026-09-20T00:00:00Z,high\n", "evidence_url"),
        ("rating,imp-a,,,,factuality,Rater,High,,2026-09-20T00:00:00Z,medium\n", "method_url"),
        ("rating,imp-a,,,,factuality,Rater,High,not-a-url,2026-09-20T00:00:00Z,medium\n", "method_url"),
        ("ownership,imp-a,TO_VERIFY,,https://a.example/about,,,,,2026-09-20T00:00:00Z,high\n", "owner_name"),
        ("ownership,imp-a,Owner A,,https://a.example/about,,,,,2026-09-20T00:00:00Z,certain\n", "confidence"),
        ("ownership,nope,Owner A,,https://a.example/about,,,,,2026-09-20T00:00:00Z,high\n", "unknown source_slug"),
        ("stance,imp-a,Owner A,,https://a.example/about,,,,,2026-09-20T00:00:00Z,high\n", "kind must be"),
    ],
)
def test_rows_without_provenance_reject_the_whole_file(db: Session, src: Source, row: str, problem: str) -> None:
    with pytest.raises(ImportRejected) as exc:
        import_csv(db, HEADER + OWN + row)  # one good row plus one bad row
    assert any(problem in e for e in exc.value.errors)
    assert _count(db, SourceOwnership) == 0  # nothing imported, not even the good row


def test_empty_file_is_rejected(db: Session, src: Source) -> None:
    with pytest.raises(ImportRejected):
        import_csv(db, HEADER)


def test_template_rows_left_blank_are_skipped(db: Session, src: Source) -> None:
    header = "kind,source_slug,outlet_name_for_reference,owner_name,evidence_url,retrieved_at,confidence\n"
    filled = "ownership,imp-a,A,Owner A,https://a.example/about,2026-09-20T00:00:00Z,high\n"
    blank = "ownership,imp-a,A,,,,\n"
    assert import_csv(db, header + filled + blank).ownership_added == 1
    with pytest.raises(ImportRejected):
        import_csv(db, header + blank)  # nothing filled in at all


def test_dimension_ownership_on_an_ownership_row_is_accepted(db: Session, src: Source) -> None:
    header = "kind,source_slug,owner_name,evidence_url,dimension,retrieved_at,confidence\n"
    row = "ownership,imp-a,Owner A,https://a.example/about,ownership,2026-09-20T00:00:00Z,high\n"
    assert import_csv(db, header + row).ownership_added == 1
    with pytest.raises(ImportRejected):  # any other stray rating field is still an error
        import_csv(db, header + row.replace(",ownership,2026", ",factuality,2026"))


def test_editorial_rating_may_link_our_methodology_section_only(db: Session, src: Source) -> None:
    header = "kind,source_slug,dimension,rater,value,method_url,retrieved_at,confidence\n"
    row = "rating,imp-a,bias,Lens editor,Right,{},2026-09-23T00:00:00Z,low\n"
    assert import_csv(db, header + row.format("/methodology#editorial")).ratings_added == 1
    for bad in ("/about", "methodology#editorial", "/methodology#Editorial Ratings"):
        with pytest.raises(ImportRejected):
            import_csv(db, header + row.format(bad))
