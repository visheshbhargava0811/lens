"""Fact-check matcher (docs/04 section 9, ADR-0040): each checkable story claim retrieves its closest
fact-checks (dense, any language), and an LLM verifier decides same_claim | related | different.
Only same_claim and related are stored. Precision first: candidates below `match.min_similarity`
never reach the verifier, and the prompt resolves doubt towards `related`.

    python -m lens.factchecks.match [--limit 40]
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from qdrant_client import QdrantClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from lens.agents.offline.evidence import clean
from lens.agents.prompts import skill
from lens.core.config_files import load_yaml
from lens.core.logging import get_logger
from lens.db.models import Claim, ClaimFactCheckMatch, FactCheck
from lens.nlp.embed import Embedder
from lens.retrieval.qdrant_store import FACT_CHECKS
from lens.schemas.analysis import FactCheckMatches

log = get_logger(__name__)
LLM = Callable[..., Any]  # lens.llm.client.structured


def candidates(qdrant: QdrantClient, embedder: Embedder, text: str, cfg: dict[str, Any]) -> list[tuple[str, float]]:
    vec = embedder.encode([text], sparse=False).dense[0]
    hits = qdrant.query_points(FACT_CHECKS, query=vec.tolist(), using="dense", limit=cfg["candidates"]).points
    return [(str(h.id), float(h.score)) for h in hits if h.score >= cfg["min_similarity"]]


def prompt(claim: str, checks: list[FactCheck]) -> str:
    rows = "\n".join(f'<fact_check ref="F{i + 1}">{clean(f.claim_reviewed)}</fact_check>' for i, f in enumerate(checks))
    return f"<claim>\n{clean(claim)}\n</claim>\n<fact_checks>\n{rows}\n</fact_checks>"


def verify(llm: LLM, claim: str, checks: list[FactCheck]) -> tuple[dict[str, tuple[str, str]], str]:
    """{fact_check_id: (verdict, rationale)} and the prompt version."""
    s = skill("factcheck_match")
    version = f"factcheck_match@{s.version}"
    out: FactCheckMatches = llm(
        "analysis", FactCheckMatches, s.text, prompt(claim, checks), run_name="factcheck.match", prompt_version=version
    )
    by_ref = {f"F{i + 1}": f for i, f in enumerate(checks)}
    return {
        str(by_ref[m.fact_check_ref].id): (m.verdict, m.rationale) for m in out.matches if m.fact_check_ref in by_ref
    }, version


def match_claims(
    session: Session, qdrant: QdrantClient, embedder: Embedder, llm: LLM, limit: int | None = None
) -> dict[str, int]:
    cfg = load_yaml("factchecks.yaml")["match"]
    claims = (
        session.execute(
            select(Claim)
            .where(Claim.checkable.is_(True), Claim.factcheck_checked_at.is_(None))
            .limit(limit or cfg["max_claims_per_run"])
        )
        .scalars()
        .all()
    )
    stats = {"claims": len(claims), "verified": 0, "stored": 0}
    for c in claims:
        cands = dict(candidates(qdrant, embedder, c.text, cfg))
        if cands:
            checks = list(session.execute(select(FactCheck).where(FactCheck.id.in_(list(cands)))).scalars())
            verdicts, version = verify(llm, c.text, checks)
            stats["verified"] += 1
            for fid, (verdict, why) in verdicts.items():
                if verdict in cfg["keep"]:
                    session.merge(
                        ClaimFactCheckMatch(
                            claim_id=c.id,
                            fact_check_id=fid,
                            similarity=cands[fid],
                            verdict=verdict,
                            verified_by_llm=True,
                            rationale=why,
                            schema_version=FactCheckMatches.SCHEMA_VERSION,
                            prompt_version=version,
                        )
                    )
                    stats["stored"] += 1
        c.factcheck_checked_at = datetime.now(UTC)
        session.flush()
    return stats


def main(argv: list[str]) -> int:
    from lens.db.session import get_engine
    from lens.llm.client import structured
    from lens.nlp.embed import get_embedder
    from lens.retrieval.qdrant_store import get_qdrant

    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None)
    a = ap.parse_args(argv)
    with Session(get_engine()) as session, session.begin():
        print(match_claims(session, get_qdrant(), get_embedder(), structured, a.limit))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))


def lookup(
    session: Session, qdrant: QdrantClient, embedder: Embedder, llm: LLM, texts: list[str]
) -> list[dict[str, Any]]:
    """Ask's factcheck node (docs/06 node 7): verified fact-checks for claims the reader asks about, as
    FactCheckRef dumps, same_claim first. The verifier runs only when a candidate clears min_similarity."""
    from lens.db.models import Source
    from lens.services.stories import fact_check_ref

    cfg = load_yaml("factchecks.yaml")["match"]
    found: dict[str, dict[str, Any]] = {}
    for text in texts[: load_yaml("factchecks.yaml")["ask"]["max_claims"]]:
        cands = dict(candidates(qdrant, embedder, text, cfg))
        if not cands:
            continue
        rows = session.execute(
            select(FactCheck, Source.name)
            .join(Source, Source.id == FactCheck.source_id)
            .where(FactCheck.id.in_(list(cands)))
        ).all()
        verdicts, _ = verify(llm, text, [fc for fc, _ in rows])
        for fc, name in rows:
            verdict = verdicts.get(str(fc.id), ("different", ""))[0]
            if verdict in cfg["keep"] and (str(fc.id) not in found or verdict == "same_claim"):
                found[str(fc.id)] = fact_check_ref(fc, name, verdict).model_dump(mode="json")
    return sorted(found.values(), key=lambda f: f["match"] != "same_claim")


def max_similarity(embedder: Embedder, texts: list[str], claims: list[str]) -> list[float]:
    """For G-GEN-06: each text's highest cosine to any of the claims."""
    import numpy as np

    vecs = embedder.encode(texts + claims, sparse=False).dense
    vecs = vecs / np.linalg.norm(vecs, axis=1, keepdims=True)
    sims = vecs[: len(texts)] @ vecs[len(texts) :].T
    return [float(x) for x in sims.max(axis=1)]
