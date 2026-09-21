"""Source registry: validate data/sources/sources.seed.yaml and load it into Postgres.

Rule 7: ownership needs an evidence URL and ratings need a method URL. TO_VERIFY placeholders
are allowed only where docs/13 allows them (terms), never in anything we act on.

Usage: uv run python -m lens.ingest.registry  (also `make seed`)
"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator, model_validator
from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from lens.core.settings import REPO_ROOT, get_settings
from lens.db.models import Source, SourceFetchState, SourceOwnership, SourceRating
from lens.db.session import get_engine

TO_VERIFY = "TO_VERIFY"
SEED_PATH = REPO_ROOT / "data/sources/sources.seed.yaml"


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class FeedEntry(_Strict):
    url: HttpUrl
    kind: Literal["rss", "sitemap"]
    topic: str | None = None
    evidence_url: HttpUrl
    found_via: str
    checked_at: datetime


class OwnershipEntry(_Strict):
    owner_name: str
    owner_type: str | None = None
    parent_group: str | None = None
    evidence_url: HttpUrl
    retrieved_at: datetime
    verified_by: str | None = None
    confidence: Literal["low", "medium", "high"]

    @field_validator("owner_name")
    @classmethod
    def _no_placeholder(cls, v: str) -> str:
        if v.strip() in ("", TO_VERIFY):
            raise ValueError("ownership owner_name must be verified, not TO_VERIFY")
        return v


class RatingEntry(_Strict):
    dimension: str
    rater: str
    value: str
    numeric_value: float | None = None
    method_url: HttpUrl
    evidence_url: HttpUrl | None = None
    retrieved_at: datetime
    confidence: Literal["low", "medium", "high"]


class Evidence(_Strict):
    feed_evidence_url: HttpUrl | None = None
    robots_url: HttpUrl | None = None
    terms_link_found: HttpUrl | None = None
    terms_evidence_url: HttpUrl | Literal["TO_VERIFY"] = "TO_VERIFY"


class SeedSource(_Strict):
    slug: str = Field(pattern=r"^[a-z0-9-]+$")
    name: str
    homepage_url: HttpUrl
    language_codes: list[str] = Field(min_length=1)
    region: str
    is_wire: bool = False
    is_fact_checker: bool = False
    license_mode: Literal["full_text", "snippet_only", "link_only"] = "snippet_only"
    image_policy: Literal["hotlink", "none"] = "none"
    robots_ok: bool
    active: bool
    inactive_reason: str | None = None
    feed_urls: list[FeedEntry] = []
    inclusion_reason: str
    evidence: Evidence
    ownership: list[OwnershipEntry] = []
    ratings: list[RatingEntry] = []

    @model_validator(mode="after")
    def _consistent(self) -> SeedSource:
        if self.active and not self.feed_urls:
            raise ValueError(f"{self.slug}: an active source needs at least one verified feed")
        if self.active and not self.robots_ok:
            raise ValueError(f"{self.slug}: robots.txt does not permit crawling; cannot be active")
        if not self.active and not self.inactive_reason:
            raise ValueError(f"{self.slug}: inactive sources must say why (inactive_reason)")
        if self.license_mode == "full_text":
            # No full-text extractor or license exists yet (docs/01 ADR-0001). Refuse rather than guess.
            raise ValueError(f"{self.slug}: full_text needs a recorded license; not supported yet")
        return self


def load_seed(path: Path = SEED_PATH) -> list[SeedSource]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or []
    sources = [SeedSource.model_validate(item) for item in raw]
    slugs = [s.slug for s in sources]
    if len(slugs) != len(set(slugs)):
        raise ValueError("duplicate slugs in seed file")
    return sources


def upsert_sources(session: Session, sources: list[SeedSource]) -> dict[str, int]:
    """Idempotent: re-running updates rows in place and keeps fetch-state validators."""
    interval = get_settings().ingest_default_interval_min
    counts = {"sources": 0, "feeds": 0, "ownership": 0, "ratings": 0}
    for s in sources:
        values = {
            "slug": s.slug,
            "name": s.name,
            "homepage_url": str(s.homepage_url),
            "language_codes": s.language_codes,
            "region": s.region,
            "feed_urls": [f.model_dump(mode="json") for f in s.feed_urls],
            "license_mode": s.license_mode,
            "image_policy": s.image_policy,
            "robots_ok": s.robots_ok,
            "is_wire": s.is_wire,
            "is_fact_checker": s.is_fact_checker,
            "active": s.active,
            "inactive_reason": s.inactive_reason,
            "evidence": s.evidence.model_dump(mode="json"),
        }
        stmt = insert(Source).values(**values)
        stmt = stmt.on_conflict_do_update(
            index_elements=[Source.slug], set_={k: stmt.excluded[k] for k in values}
        )
        source_id = session.execute(stmt.returning(Source.id)).scalar_one()
        counts["sources"] += 1

        urls = [str(f.url) for f in s.feed_urls]
        session.execute(
            delete(SourceFetchState).where(
                SourceFetchState.source_id == source_id, SourceFetchState.feed_url.not_in(urls)
            )
        )
        for f in s.feed_urls:
            fs = insert(SourceFetchState).values(
                source_id=source_id, feed_url=str(f.url), kind=f.kind, interval_min=interval
            )
            session.execute(
                fs.on_conflict_do_update(
                    index_elements=[SourceFetchState.source_id, SourceFetchState.feed_url],
                    set_={"kind": fs.excluded.kind, "interval_min": fs.excluded.interval_min},
                )
            )
            counts["feeds"] += 1

        # Provenance rows are replaced wholesale from the seed (it is the reviewed source of truth).
        session.execute(delete(SourceOwnership).where(SourceOwnership.source_id == source_id))
        session.execute(delete(SourceRating).where(SourceRating.source_id == source_id))
        for o in s.ownership:
            session.add(SourceOwnership(source_id=source_id, **o.model_dump(mode="json")))
            counts["ownership"] += 1
        for r in s.ratings:
            session.add(SourceRating(source_id=source_id, **r.model_dump(mode="json")))
            counts["ratings"] += 1
    return counts


def main() -> int:
    sources = load_seed()
    with Session(get_engine()) as session, session.begin():
        counts = upsert_sources(session, sources)
        active = session.execute(select(Source.slug).where(Source.active)).scalars().all()
    print(f"seeded {counts} ({len(active)} active)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
