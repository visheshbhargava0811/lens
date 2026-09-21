import copy
from typing import Any

import pytest
from pydantic import ValidationError

from lens.ingest.registry import SeedSource, load_seed

BASE: dict[str, Any] = {
    "slug": "x",
    "name": "X",
    "homepage_url": "https://x.example/",
    "language_codes": ["en"],
    "region": "national",
    "robots_ok": True,
    "active": True,
    "feed_urls": [
        {
            "url": "https://x.example/rss",
            "kind": "rss",
            "evidence_url": "https://x.example/rss-index",
            "found_via": "rss-index-page",
            "checked_at": "2026-09-21T00:00:00Z",
        }
    ],
    "inclusion_reason": "test",
    "evidence": {"feed_evidence_url": "https://x.example/rss-index"},
}


def _with(**kw: Any) -> dict[str, Any]:
    d = copy.deepcopy(BASE)
    d.update(kw)
    return d


def test_real_seed_file_validates() -> None:
    sources = load_seed()
    assert sum(s.active for s in sources) >= 15
    assert {lang for s in sources if s.active for lang in s.language_codes} >= {"en", "hi", "mr"}


def test_ownership_without_evidence_is_rejected() -> None:
    bad = _with(
        ownership=[{"owner_name": "Some Group", "retrieved_at": "2026-09-21T00:00:00Z", "confidence": "low"}]
    )
    with pytest.raises(ValidationError, match="evidence_url"):
        SeedSource.model_validate(bad)


def test_ownership_placeholder_is_rejected() -> None:
    bad = _with(
        ownership=[
            {
                "owner_name": "TO_VERIFY",
                "evidence_url": "https://e.example",
                "retrieved_at": "2026-09-21T00:00:00Z",
                "confidence": "low",
            }
        ]
    )
    with pytest.raises(ValidationError, match="TO_VERIFY"):
        SeedSource.model_validate(bad)


def test_rating_without_method_url_is_rejected() -> None:
    bad = _with(
        ratings=[
            {
                "dimension": "factuality",
                "rater": "R",
                "value": "High",
                "retrieved_at": "2026-09-21T00:00:00Z",
                "confidence": "low",
            }
        ]
    )
    with pytest.raises(ValidationError, match="method_url"):
        SeedSource.model_validate(bad)


@pytest.mark.parametrize(
    ("override", "message"),
    [
        ({"feed_urls": []}, "at least one verified feed"),
        ({"robots_ok": False}, "robots"),
        ({"active": False}, "inactive_reason"),
        ({"license_mode": "full_text"}, "license"),
        (
            {
                "feed_urls": [
                    {
                        "url": "TO_VERIFY",
                        "kind": "rss",
                        "evidence_url": "TO_VERIFY",
                        "found_via": "x",
                        "checked_at": "2026-09-21T00:00:00Z",
                    }
                ]
            },
            "URL",
        ),
    ],
)
def test_invalid_sources_are_rejected(override: dict[str, Any], message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        SeedSource.model_validate(_with(**override))
