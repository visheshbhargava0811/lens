"""Phase 8 fact-checks: ingest parsing and rating normalization (docs/04 section 9, docs/13)."""

from typing import Any

import pytest

from lens.core.config_files import load_yaml
from lens.factchecks.ingest import normalize_rating, reviews

TABLE = load_yaml("factchecks.yaml")["ratings"]


def test_ratings_normalize_but_keep_their_wording() -> None:
    assert normalize_rating("False", TABLE) == "false"
    assert normalize_rating("MISLEADING", TABLE) == "misleading"
    assert normalize_rating("Half True.", TABLE) == "misleading"
    assert normalize_rating("भ्रामक", TABLE) == "misleading"
    assert normalize_rating("फर्जी", TABLE) == "false"
    assert normalize_rating("Satire-ish", TABLE) == "other"  # unknown wording is never guessed
    assert normalize_rating(None, TABLE) == "other"


def test_only_the_fact_checkers_own_pages_are_kept() -> None:
    payload = {
        "claims": [
            {
                "text": "Video shows <b>X</b>",
                "claimReview": [
                    {
                        "url": "https://www.indiatoday.in/fact-check/story/a",
                        "publisher": {"site": "indiatoday.in"},
                        "textualRating": "False",
                        "reviewDate": "2026-09-20T10:00:00Z",
                        "languageCode": "en",
                    },
                    {
                        "url": "https://www.indiatoday.in/india/story/b",
                        "publisher": {"site": "indiatoday.in"},
                        "textualRating": "False",
                    },  # a news page on the same site
                    {
                        "url": "https://other.example/c",
                        "publisher": {"site": "other.example"},
                        "textualRating": "False",
                    },
                ],
            },
            {
                "claimReview": [
                    {"url": "https://www.indiatoday.in/fact-check/story/d", "publisher": {"site": "indiatoday.in"}}
                ]
            },
        ]
    }
    got = list(reviews(payload, ["indiatoday.in"], "/fact-check/"))
    assert [r.url for r in got] == ["https://www.indiatoday.in/fact-check/story/a"]  # no claim text: skipped
    assert got[0].claim == "Video shows X" and got[0].published_at is not None and got[0].language == "en"


def test_matcher_stores_only_verified_matches_and_story_shows_same_claim_first(
    db: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    from datetime import UTC, datetime

    from qdrant_client import QdrantClient
    from sqlalchemy import select

    from lens.db.models import Claim, ClaimFactCheckMatch, FactCheck, Source, StoryArticle
    from lens.factchecks.ingest import index
    from lens.factchecks.match import match_claims
    from lens.nlp.embed import HashEmbedder
    from lens.retrieval.qdrant_store import ensure_collections
    from lens.schemas.analysis import FactCheckMatch, FactCheckMatches
    from lens.services.stories import story_fact_checks
    from tests.test_api_public import _src, _story

    q = QdrantClient(":memory:")
    ensure_collections(q, dim=HashEmbedder.dim, colbert_dim=HashEmbedder.dim)
    story = _story(db, [_src(db, "fc-news")])
    art = db.execute(select(StoryArticle.article_id).where(StoryArticle.story_id == story.id)).scalar_one()
    checker = Source(
        slug="fc-boom", name="BOOM", homepage_url="https://boom.example", language_codes=[], is_fact_checker=True
    )
    db.add(checker)
    db.flush()
    texts = ["Video shows the bridge collapse in Bihar", "Bridge collapse photo is from 2019", "Budget cuts rail fares"]
    checks = [
        FactCheck(
            source_id=checker.id,
            url=f"https://boom.example/{i}",
            claim_reviewed=t,
            rating_original="False",
            rating_normalized="false",
            published_at=datetime(2026, 9, 20 + i, tzinfo=UTC),
            language="en",
        )
        for i, t in enumerate(texts)
    ]
    db.add_all(checks)
    claim = Claim(
        article_id=art,
        text="Video shows the bridge collapse in Bihar",
        source_quote="x",
        char_start=0,
        char_end=1,
        checkable=True,
        schema_version="1.0",
    )
    db.add(claim)
    db.flush()
    index(q, HashEmbedder(), checks)
    calls: list[str] = []

    def llm(tier: str, model: type, system: str, user: str, **kw: Any) -> FactCheckMatches:
        calls.append(user)
        refs = {
            t: f"F{i + 1}"
            for i, t in enumerate(
                line.split(">", 1)[1].split("<")[0] for line in user.splitlines() if line.startswith("<fact_check ")
            )
        }
        verdict = {texts[0]: "same_claim", texts[1]: "related", texts[2]: "different"}
        return FactCheckMatches(
            matches=[FactCheckMatch(fact_check_ref=r, rationale="r", verdict=verdict[t]) for t, r in refs.items()]
        )

    m_cfg = {"candidates": 5, "min_similarity": -1.0, "keep": ["same_claim", "related"], "max_claims_per_run": 10}
    monkeypatch.setattr("lens.factchecks.match.load_yaml", lambda name: {"match": m_cfg})
    stats = match_claims(db, q, HashEmbedder(), llm)
    assert stats == {"claims": 1, "verified": 1, "stored": 2} and len(calls) == 1
    verdicts = sorted(r.verdict for r in db.execute(select(ClaimFactCheckMatch)).scalars())
    assert verdicts == ["related", "same_claim"]  # `different` is never stored
    assert claim.factcheck_checked_at is not None
    shown = story_fact_checks(db, [story.id])
    assert [f.match for f in shown] == ["same_claim", "related"] and shown[0].fact_checker == "BOOM"
    assert shown[0].rating == "False" and shown[0].url.startswith("https://boom.example/")
    assert match_claims(db, q, HashEmbedder(), llm, limit=5)["claims"] == 0  # checked claims are not re-verified
