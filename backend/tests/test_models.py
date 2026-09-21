"""The ORM must stay in sync with the reference DDL in docs/03."""

from lens.db.models import Base, LicenseMode, Source

DOC_TABLES = {
    "sources",
    "source_ownership",
    "source_ratings",
    "articles",
    "chunks",
    "stories",
    "story_articles",
    "story_stats",
    "claims",
    "framings",
    "fact_checks",
    "claim_fact_check_matches",
    "story_summaries",
    "users",
    "user_preferences",
    "story_views",
    "ask_turns",
    "guard_events",
    "review_queue",
    "feedback",
    "dead_letters",
    "source_fetch_state",  # ADR-0012
}


def test_all_doc_tables_present() -> None:
    assert set(Base.metadata.tables) == DOC_TABLES


def test_license_mode_defaults_to_snippet_only() -> None:
    col = Source.__table__.c.license_mode
    assert col.server_default is not None
    assert col.server_default.arg == LicenseMode.snippet_only.value


def test_provenance_columns_required() -> None:
    """Rule 7: ratings and ownership need provenance."""
    ratings = Base.metadata.tables["source_ratings"].c
    ownership = Base.metadata.tables["source_ownership"].c
    for col in (ratings.rater, ratings.method_url, ratings.retrieved_at, ratings.confidence):
        assert not col.nullable
    for col in (ownership.evidence_url, ownership.retrieved_at, ownership.confidence):
        assert not col.nullable
