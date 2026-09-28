"""Run the story analysis graph over eligible stories and store the results (ADR-0022).

Eligible: visible stories with at least `analysis.min_sources` sources that have no analysis yet,
or that gained `reanalysis_trigger.new_sources` sources since the last one. Each story is one
transaction: claims (G-GEN-02 verified), a new versioned summary row, its guard events, and a
review-queue item when G-OUT-07 holds it. Failures are stored too, so a story is not retried on
every pass until it changes.

Usage: make analyze  (also runs inside `make pipeline-worker`)
"""

from __future__ import annotations

import sys
import time
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import Session

from lens.agents.offline.evidence import ArticleIn, EvidenceArticle, normalize, quote_span, select_evidence
from lens.agents.offline.story_graph import LLM, StoryState, build
from lens.core.config_files import load_yaml
from lens.core.logging import configure_logging, get_logger
from lens.db.models import Article, Claim, GuardEvent, ReviewQueueItem, Source, Story, StoryArticle, StorySummary
from lens.db.session import get_engine
from lens.llm.client import structured, tier
from lens.ops import kill
from lens.pipeline.stats import best_ratings
from lens.schemas.analysis import CitedSentence, ClaimList, SummaryDraft
from lens.stats.coverage import BIAS_BUCKETS, bucket

log = get_logger(__name__)


def eligible(session: Session, limit: int) -> list[Story]:
    c = load_yaml("clustering.yaml")
    # A failed analysis counts only while it is recent, so transient provider errors are retried later.
    retry_after = datetime.now(UTC) - timedelta(hours=c["reanalysis_trigger"]["hours"])
    last = (
        select(StorySummary.story_id, func.max(StorySummary.source_count).label("n"))
        .where(
            or_(StorySummary.state != "failed", StorySummary.created_at > retry_after),
            # Failures caused by exhausted providers are not about the story: never block a retry.
            ~StorySummary.verifier_result["errors"].astext.contains("every provider failed"),
        )
        .group_by(StorySummary.story_id)
        .subquery()
    )
    off_topics = sorted(kill.generation(session).off_topics)  # G-OPS-03
    q = (
        select(Story)
        .outerjoin(last, last.c.story_id == Story.id)
        .where(
            Story.kill_switch.is_(False),
            or_(Story.topic.is_(None), Story.topic.not_in(off_topics)),
            Story.source_count >= c["analysis"]["min_sources"],
            or_(last.c.n.is_(None), Story.source_count - last.c.n >= c["reanalysis_trigger"]["new_sources"]),
        )
        .order_by(last.c.n.is_not(None), Story.source_count.desc(), Story.last_updated_at.desc())
        .limit(limit)
    )
    return list(session.execute(q).scalars())


def load_articles(session: Session, story: Story) -> list[ArticleIn]:
    rows = session.execute(
        select(Article, Source)
        .join(StoryArticle, StoryArticle.article_id == Article.id)
        .join(Source, Source.id == Article.source_id)
        .where(StoryArticle.story_id == story.id)
    ).all()
    value_map = load_yaml("guardrails.yaml")["stats"]["bias_value_map"]
    biases = best_ratings(session, "bias", list({s.id for _, s in rows}))
    return [
        ArticleIn(
            article_id=str(a.id),
            source_id=str(s.id),
            source_name=s.name,
            language=a.language,
            published_at=a.published_at,
            title=a.title,
            snippet=a.snippet,
            bias=bucket(biases[s.id].value if s.id in biases else None, value_map, BIAS_BUCKETS),
        )
        for a, s in rows
    ]


def _cite(sentences: list[CitedSentence], by_ref: dict[str, EvidenceArticle]) -> list[dict[str, Any]]:
    """Refs -> article ids and outlet names, re-attached in code (the model never saw them)."""
    return [
        {
            "text": s.text,
            "citations": [
                {"ref": r, "article_id": by_ref[r].article.article_id, "source_name": by_ref[r].article.source_name}
                for r in s.citations
            ],
        }
        for s in sentences
    ]


def store(session: Session, story: Story, state: StoryState) -> StorySummary:
    by_ref = {e.ref: e for e in state["evidence"]}
    versions = state.get("prompt_versions", {})

    # Claims: replace this story's evidence articles' claims with the verified set.
    article_ids = [uuid.UUID(e.article.article_id) for e in state["evidence"]]
    session.execute(delete(Claim).where(Claim.article_id.in_(article_ids)))
    for c in state.get("claims", []):
        e = by_ref[c.article_ref]
        span = quote_span(c.source_quote, e.text)
        if span is None:  # G-GEN-02 already dropped these; never store an unverified quote
            continue
        session.add(
            Claim(
                article_id=uuid.UUID(e.article.article_id),
                text=c.text,
                source_quote=normalize(c.source_quote),
                char_start=span[0],
                char_end=span[1],
                attributed_to=c.attributed_to,
                checkable=c.checkable,
                schema_version=ClaimList.SCHEMA_VERSION,
                prompt_version=versions.get("claims_extraction"),
            )
        )

    summary: SummaryDraft | None = state.get("summary")
    framing = state.get("framing")
    version = (
        session.execute(select(func.max(StorySummary.version)).where(StorySummary.story_id == story.id)).scalar() or 0
    ) + 1
    verdict = state.get("verdict")
    row = StorySummary(
        story_id=story.id,
        version=version,
        lang="en",
        summary=_cite(summary.summary, by_ref) if summary else [],
        agreements=_cite(summary.agreements, by_ref) if summary else [],
        disagreements=_cite(summary.disagreements, by_ref) if summary else [],
        framing={
            "differences": _cite(framing.framing_differences, by_ref),
            "only_in_some": _cite(framing.only_in_some_coverage, by_ref),
        }
        if framing
        else None,
        # The models that actually produced this version (primary or fallback), for the audit trail.
        model=";".join(
            f"{task}={m.get('provider')}/{m.get('model')}" for task, m in sorted(state.get("models", {}).items())
        )
        or f"{tier('synthesis').model}; judge {tier('judge').model}",
        prompt_version=";".join(f"{k}={v}" for k, v in sorted(versions.items())),
        verifier_result={
            "verdict": verdict.model_dump() if verdict else None,
            "attempts": state.get("attempts", 0),
            "pruned": _cite(state.get("pruned", []), by_ref),  # kept with citations for judge calibration
            "errors": state.get("errors", []),
        },
        state=state["outcome"],
        source_count=story.source_count,
        schema_version=SummaryDraft.SCHEMA_VERSION,
    )
    session.add(row)
    session.flush()

    for g in state.get("guards", []):
        session.add(
            GuardEvent(
                run_id=g.run_id or f"story:{story.id}:v{version}",
                guard_id=g.guard_id,
                stage="story_analysis",
                passed=g.passed,
                action=g.action,
                reason=g.reason,
                score=g.score,
                meta={"story_id": str(story.id), "summary_version": version, **g.meta},
            )
        )
    if state["outcome"] == "review":
        reason = next((g.reason for g in state.get("guards", []) if g.guard_id == "G-OUT-07"), "sensitive topic")
        session.add(ReviewQueueItem(kind="story_summary", ref_id=row.id, reason=reason))
    return row


def _providers_exhausted(state: StoryState) -> bool:
    """The summary or judge step failed because every configured provider failed (quota, outage)."""
    return any(
        e.split(":", 1)[0] in ("summary", "judge") and "every provider failed" in e for e in state.get("errors", [])
    )


def analyze_pending(llm: LLM = structured, limit: int | None = None) -> dict[str, int]:
    cfg = load_yaml("clustering.yaml")["analysis"]
    keywords = load_yaml("guardrails.yaml")["sensitive_keywords"]
    graph = build(llm)
    counts = {"published": 0, "review": 0, "failed": 0, "deferred": 0}
    with Session(get_engine()) as session:
        if kill.generation(session).off:  # G-OPS-03 global kill switch
            return counts
        stories = eligible(session, limit or cfg["max_stories_per_run"])
    deadline = time.monotonic() + cfg["max_seconds_per_run"]
    for story in stories:
        if time.monotonic() > deadline:
            break  # the rest wait for the next pass
        # Read, then call the models with no transaction open (calls take tens of seconds), then write.
        with Session(get_engine()) as session:
            evidence = select_evidence(load_articles(session, story), cfg["max_articles"])
        state: StoryState = graph.invoke(
            {
                "story_id": str(story.id),
                "headline": story.headline,
                "evidence": evidence,
                "sensitive_keywords": keywords,
            }
        )
        if state["outcome"] == "failed" and _providers_exhausted(state):
            # Circuit breaker: not this story's fault. Store nothing (so it is retried next pass)
            # and stop, instead of burning the remaining quota on the next stories.
            counts["deferred"] += 1
            log.warning("pipeline.analyze.providers_exhausted", story=story.slug, errors=state.get("errors"))
            break
        with Session(get_engine()) as session, session.begin():
            fresh = session.get_one(Story, story.id)
            row = store(session, fresh, state)
            counts[row.state] += 1
            log.info(
                "pipeline.analyze", story=fresh.slug, outcome=row.state, version=row.version, errors=state.get("errors")
            )
    return counts


def main() -> int:
    configure_logging("INFO", json=False)
    print(analyze_pending(limit=int(sys.argv[1]) if len(sys.argv) > 1 else None))
    return 0


if __name__ == "__main__":
    sys.exit(main())
