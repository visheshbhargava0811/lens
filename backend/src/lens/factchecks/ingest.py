"""Fact-check ingest (docs/04 section 9, ADR-0040): ClaimReview items from the Google Fact Check Tools API
for the fact-checkers in data/sources/fact_checkers.yaml, stored in `fact_checks` and embedded
(`claim_reviewed`, BGE-M3 dense) into Qdrant `fact_checks` for the matcher.

Only ClaimReview metadata is kept: the claim, the fact-checker's own rating (plus a normalized one),
the date and the link. The UI always attributes the fact-checker and links out (docs/13).

    python -m lens.factchecks.ingest [--days 180]
"""

from __future__ import annotations

import argparse
import sys
import time
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import httpx
import yaml
from qdrant_client import QdrantClient, models
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from lens.agents.offline.evidence import clean
from lens.core.config_files import load_yaml
from lens.core.logging import get_logger
from lens.core.settings import REPO_ROOT, get_settings
from lens.db.models import FactCheck, LicenseMode, Source
from lens.ingest.http import user_agent
from lens.nlp.embed import Embedder
from lens.retrieval.qdrant_store import FACT_CHECKS, iso

log = get_logger(__name__)
API = "https://factchecktools.googleapis.com/v1alpha1/claims:search"
SEED = REPO_ROOT / "data" / "sources" / "fact_checkers.yaml"


@dataclass(frozen=True)
class Review:
    url: str
    claim: str
    rating: str | None
    published_at: datetime | None
    language: str | None


def normalize_rating(rating: str | None, table: dict[str, list[str]]) -> str:
    """The fact-checker's wording -> true | false | misleading | unproven | other (docs/13)."""
    r = (rating or "").strip().lower().rstrip(".!")
    for norm, words in table.items():
        if r in (str(w).lower() for w in words):
            return norm
    return "other"


def _date(s: str | None) -> datetime | None:
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")) if s else None
    except ValueError:
        return None


def reviews(payload: dict[str, Any], sites: list[str], url_contains: str | None) -> Iterator[Review]:
    for c in payload.get("claims", []):
        for cr in c.get("claimReview", []):
            url = cr.get("url") or ""
            site = (cr.get("publisher") or {}).get("site") or ""
            if site not in sites or (url_contains and url_contains not in url) or not c.get("text"):
                continue
            if not url.startswith("https://"):  # only https links reach the page (XSS)
                continue
            yield Review(
                url=url,
                claim=clean(c["text"]),
                rating=cr.get("textualRating"),
                published_at=_date(cr.get("reviewDate") or c.get("claimDate")),
                language=cr.get("languageCode"),
            )


def search_site(client: httpx.Client, key: str, site: str, days: int, cfg: dict[str, Any]) -> Iterator[dict[str, Any]]:
    """Pages through one publisher site; retries 503s (the API sheds bursts) and paces calls."""
    token: str | None = None
    while True:
        params: dict[str, Any] = {
            "reviewPublisherSiteFilter": site,
            "maxAgeDays": days,
            "pageSize": cfg["page_size"],
            "key": key,
        }
        if token:
            params["pageToken"] = token
        for attempt in range(cfg["retries"]):
            r = client.get(API, params=params)
            if r.status_code == 200:
                break
            time.sleep(2**attempt * 2)
        else:
            raise RuntimeError(f"fact check API {site}: HTTP {r.status_code}")
        data = r.json()
        yield data
        time.sleep(cfg["min_seconds_between_calls"])
        token = data.get("nextPageToken")
        if not token:
            return


def upsert_sources(session: Session, seed: list[dict[str, Any]]) -> dict[str, Source]:
    out = {}
    for fc in seed:
        src = session.execute(select(Source).where(Source.slug == fc["slug"])).scalar_one_or_none()
        if src is None:
            src = Source(slug=fc["slug"], name=fc["name"], homepage_url=f"https://{fc['sites'][0]}/", language_codes=[])
            session.add(src)
        src.is_fact_checker, src.license_mode, src.active = True, LicenseMode.link_only, False
        src.inactive_reason = "Fact-checker: ClaimReview via the Google Fact Check Tools API, no feed polling."
        src.evidence = {"api": API, "sites": fc["sites"], "evidence_url": fc["evidence_url"]}
        out[fc["slug"]] = src
    session.flush()
    return out


def ingest(session: Session, qdrant: QdrantClient, embedder: Embedder, days: int | None = None) -> dict[str, int]:
    cfg, table = load_yaml("factchecks.yaml")["ingest"], load_yaml("factchecks.yaml")["ratings"]
    key = get_settings().google_factcheck_api_key
    if key is None:
        raise RuntimeError("GOOGLE_FACTCHECK_API_KEY is not set")
    seed = yaml.safe_load(SEED.read_text())["fact_checkers"]
    sources = upsert_sources(session, seed)
    stats = {"seen": 0, "new": 0}
    new: list[FactCheck] = []
    with httpx.Client(timeout=30, headers={"User-Agent": user_agent()}) as http:
        for fc in seed:
            src = sources[fc["slug"]]
            for site in fc["sites"]:
                for page in search_site(http, key.get_secret_value(), site, days or cfg["max_age_days"], cfg):
                    for rv in reviews(page, [site], fc.get("url_contains")):
                        stats["seen"] += 1
                        row = session.execute(
                            insert(FactCheck)
                            .values(
                                source_id=src.id,
                                url=rv.url,
                                claim_reviewed=rv.claim,
                                rating_original=rv.rating,
                                rating_normalized=normalize_rating(rv.rating, table),
                                published_at=rv.published_at,
                                language=rv.language,
                            )
                            .on_conflict_do_nothing(index_elements=["url"])
                            .returning(FactCheck.id)
                        ).scalar_one_or_none()
                        if row is not None:
                            new.append(session.get(FactCheck, row))  # type: ignore[arg-type]
            log.info("factchecks.site_done", fact_checker=fc["slug"], seen=stats["seen"])
    if new:
        index(qdrant, embedder, new)
    stats["new"] = len(new)
    return stats


def index(qdrant: QdrantClient, embedder: Embedder, rows: list[FactCheck]) -> None:
    for i in range(0, len(rows), 64):
        batch = rows[i : i + 64]
        vecs = embedder.encode([r.claim_reviewed for r in batch], sparse=False).dense
        qdrant.upsert(
            FACT_CHECKS,
            points=[
                models.PointStruct(
                    id=str(r.id),
                    vector={"dense": v.tolist()},
                    payload={
                        "fact_check_id": str(r.id),
                        "source_id": str(r.source_id),
                        "language": r.language,
                        "published_at": iso(r.published_at) if r.published_at else None,
                    },
                )
                for r, v in zip(batch, vecs, strict=True)
            ],
        )


def main(argv: list[str]) -> int:
    from lens.db.session import get_engine
    from lens.nlp.embed import get_embedder
    from lens.retrieval.qdrant_store import get_qdrant

    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=None, help="look-back (default ingest.max_age_days)")
    a = ap.parse_args(argv)
    with Session(get_engine()) as session, session.begin():
        print(ingest(session, get_qdrant(), get_embedder(), a.days))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
