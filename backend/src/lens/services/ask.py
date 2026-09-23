"""Ask service: wires the Ask graph to Qdrant and Postgres, and turns its final state into the
`/ask` SSE events (docs/09). Citations, limitations and coverage are computed here, by code.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel
from qdrant_client import QdrantClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from lens.agents.offline.evidence import ArticleIn, EvidenceArticle, article_text
from lens.agents.online.ask_graph import AskState, Evidence, build
from lens.core.config_files import load_yaml
from lens.db.models import Article, Chunk, LicenseMode, Source, Story
from lens.llm.client import structured
from lens.nlp.embed import Embedder
from lens.pipeline.stats import best_ratings
from lens.retrieval.pipeline import retrieve
from lens.schemas import api
from lens.schemas.analysis import CitedSentence
from lens.schemas.ask import SECTIONS
from lens.services.stories import (
    M_BIAS,
    cited_api,
    coverage_bar,
    find_story,
    story_cards,
    story_detail,
    visible_story,
)
from lens.stats.coverage import BIAS_BUCKETS, bucket, rated_share_confidence

ABSTAIN_MESSAGES = {  # docs/10 copy
    "insufficient_coverage": "There isn't enough reliable coverage to answer this yet. "
    "Here are the closest stories we found.",
    "out_of_scope": "Lens covers news reporting. Try asking what outlets have reported about a story.",
    "service_unavailable": "Lens can't answer right now. Please try again in a few minutes.",
    "sensitive_topic_under_review": "This topic is sensitive, so we only show reviewed summaries. "
    "This one is still being reviewed.",
}
STATUS_BY_NODE: dict[str, tuple[Literal["searching", "verifying"], str]] = {
    "understand": ("searching", "Searching coverage"),
    "synthesize": ("verifying", "Checking every sentence against its sources"),
}


def bias_by_source(session: Session) -> dict[str, str]:
    value_map = load_yaml("guardrails.yaml")["stats"]["bias_value_map"]
    return {str(sid): bucket(r.value, value_map, BIAS_BUCKETS) for sid, r in best_ratings(session, "bias").items()}


def make_retriever(
    session: Session, client: QdrantClient, embedder: Embedder, now: Callable[[], datetime]
) -> Callable[[str, int], Evidence]:
    cfg, bias_of = load_yaml("retrieval.yaml"), bias_by_source(session)

    def run(query: str, window_days: int) -> Evidence:
        r = retrieve(client, embedder, query, bias_of, cfg, now(), window_days)
        ids = [uuid.UUID(h.article_id) for h in r.hits]
        rows = {
            str(a.id): (a, s)
            for a, s in session.execute(select(Article, Source).join(Source).where(Article.id.in_(ids)))
        }
        arts = []
        for h in r.hits:
            if h.article_id not in rows:
                continue
            a, s = rows[h.article_id]
            # G-EV-06: link_only sources contribute their headline only; nothing else is shown or sent.
            snippet = None if s.license_mode == LicenseMode.link_only else a.snippet
            arts.append(
                ArticleIn(
                    str(a.id),
                    str(s.id),
                    s.name,
                    a.language,
                    a.published_at,
                    a.title,
                    snippet,
                    bias_of.get(str(s.id), "unrated"),
                )
            )
        evidence = [EvidenceArticle(f"A{i + 1}", x, article_text(x.title, x.snippet)) for i, x in enumerate(arts)]
        return Evidence(evidence, r.story_ids, r.scope, r.top_score, [s for s, _ in r.stories])

    return run


def make_stored_summary(session: Session) -> Callable[[list[str]], dict[str, Any] | None]:
    def run(story_ids: list[str]) -> dict[str, Any] | None:
        for sid in story_ids:
            story = find_story(session, sid)
            if story is None:
                continue
            detail = story_detail(session, story)
            if detail.summary is not None:
                return {"story_id": sid, "detail": detail}
        return None

    return run


def initial_state(query: str) -> AskState:
    windows = load_yaml("retrieval.yaml")["retry"]["widen_window_days"]
    return {"raw_query": query, "windows": list(windows), "guards": [], "errors": [], "pruned": []}


# ---------------------------------------------------------------- assembling events


def _stored_shape(sentences: list[CitedSentence], by_ref: dict[str, EvidenceArticle]) -> list[dict[str, Any]]:
    return [
        {
            "text": s.text,
            "citations": [
                {"ref": r, "article_id": by_ref[r].article.article_id, "source_name": by_ref[r].article.source_name}
                for r in s.citations
                if r in by_ref
            ],
        }
        for s in sentences
    ]


def _chunk_of(session: Session, article_ids: list[str]) -> dict[str, str]:
    q = select(Chunk.article_id, Chunk.id).where(
        Chunk.article_id.in_([uuid.UUID(i) for i in article_ids]), Chunk.idx == 0
    )
    return {str(a): str(c) for a, c in session.execute(q).all()}


def evidence_coverage(ev: Evidence) -> api.CoverageAvailable | api.CoverageLimited:
    """The coverage bar over the outlets in the evidence set (distinct sources, outlet-level bias)."""
    g = load_yaml("guardrails.yaml")
    by_source = {a.article.source_id: a.article.bias for a in ev.articles}
    counts = {k: 0 for k in (*BIAS_BUCKETS, "unrated")}
    for b in by_source.values():
        counts[b if b in counts else "unrated"] += 1
    conf = rated_share_confidence(counts, g["stats"]["rated_share_confidence"])
    return coverage_bar(counts, len(by_source), conf, g)


def evidence_event(ev: Evidence) -> api.AskEvidence:
    seen: dict[str, api.AskSource] = {}
    for a in ev.articles:
        seen.setdefault(
            a.article.source_id,
            api.AskSource(
                source_id=a.article.source_id,
                name=a.article.source_name,
                language=a.article.language,
                bias=a.article.bias if a.article.bias in BIAS_BUCKETS else "unrated",
            ),
        )
    newest = max((a.article.published_at for a in ev.articles), default=None)
    return api.AskEvidence(
        story_ids=ev.story_ids,
        sources=list(seen.values()),
        stale=False,
        newest_article_at=newest,
        methodology_url=M_BIAS,
    )


def cited_articles(session: Session, answer: api.AskAnswer) -> list[api.AskArticle]:
    sections = (answer.tldr, answer.what_happened, answer.agreements, answer.disagreements, answer.premises_addressed)
    ids = list(dict.fromkeys(c.article_id for sec in sections for s in sec for c in s.citations))
    if not ids:
        return []
    rows = session.execute(
        select(Article, Source).join(Source).where(Article.id.in_([uuid.UUID(i) for i in ids]))
    ).all()
    by_id = {
        str(a.id): api.AskArticle(
            id=str(a.id),
            headline=a.title,
            headline_lang=a.language,
            url=a.url,
            source_name=s.name,
            source_language=(s.language_codes or [a.language])[0],
        )
        for a, s in rows
    }
    return [by_id[i] for i in ids if i in by_id]


def answer_event(session: Session, state: AskState) -> api.AskAnswer:
    ev, d, qu = state["evidence"], state["draft"], state["qu"]
    assert ev is not None and d is not None and qu is not None
    by_ref = {a.ref: a for a in ev.articles}
    found = [p.evidence_says for p in d.premises if p.evidence_says is not None]
    sections = [_stored_shape(getattr(d, k), by_ref) for k in SECTIONS] + [_stored_shape(found, by_ref)]
    ids = sorted({c["article_id"] for sec in sections for s in sec for c in s["citations"]})
    tldr, what, agree, disagree, premises = cited_api(sections, _chunk_of(session, ids))

    g = load_yaml("guardrails.yaml")
    limitations = [
        f"None of the retrieved articles report that {p.premise}." for p in d.premises if p.evidence_says is None
    ]
    n_sources = len({a.article.source_id for a in ev.articles})
    if n_sources < g["min_sources_for_bar"]:
        limitations.append(f"Limited coverage: this answer draws on {n_sources} outlet(s).")
    if ev.scope == "global":
        limitations.append("No single story matched the question closely; this answer draws on related coverage.")
    if state.get("pruned"):
        limitations.append("Some sentences were removed because they could not be verified against their sources.")
    limitations.append("Based on headlines and short feed summaries, not full articles.")
    return api.AskAnswer(
        basis="live",
        tldr=tldr,
        what_happened=what,
        agreements=agree,
        disagreements=disagree,
        premises_addressed=premises,
        limitations=limitations,
        follow_up_questions=d.follow_up_questions[:3],
        coverage=evidence_coverage(ev),
        fact_checks=[],
        story_ids=ev.story_ids,
        articles=[],
        verified=True,
    )


def fallback_event(state: AskState) -> api.AskAnswer:
    fb, qu = state["fallback"], state["qu"]
    assert fb is not None and qu is not None
    detail: api.StoryDetail = fb["detail"]
    assert detail.summary is not None
    s = detail.summary
    limitations = [
        "A live answer to your question could not be verified, so this is the story's verified summary instead.",
        *(f"This summary does not address whether {p}." for p in qu.removed_premises),
        *detail.limitations,
    ]
    return api.AskAnswer(
        basis="stored_summary",
        tldr=s.sentences[:1],
        what_happened=s.sentences[1:],
        agreements=s.agreements,
        disagreements=s.disagreements,
        premises_addressed=[],
        limitations=limitations,
        follow_up_questions=[],
        coverage=detail.story.coverage,
        fact_checks=detail.fact_checks,
        story_ids=[fb["story_id"]],
        articles=[],
        verified=True,
    )


def abstain_event(session: Session, state: AskState) -> api.AskAbstain:
    reason = state.get("abstain_reason") or "insufficient_coverage"
    ev = state.get("evidence")
    closest: list[api.StoryCard] = []
    if ev is not None and ev.closest_story_ids and reason in ("insufficient_coverage", "sensitive_topic_under_review"):
        ids = [uuid.UUID(i) for i in ev.closest_story_ids]
        cards = {c.id: c for c in story_cards(session, select(Story).where(visible_story(), Story.id.in_(ids)))}
        closest = [cards[i] for i in ev.closest_story_ids if i in cards]
    return api.AskAbstain(reason=reason, message=ABSTAIN_MESSAGES[reason], closest_stories=closest)


def ask_events(session: Session, query: str, graph: Any) -> Iterator[tuple[str, BaseModel]]:
    """Runs the graph and yields (event, payload) for SSE. Only verified answers are ever sent."""
    yield "status", api.AskStatus(step="understanding", message="Understanding the question")
    state: dict[str, Any] = dict(initial_state(query))
    sent_status: set[str] = set()
    for update in graph.stream(state, stream_mode="updates"):
        for node, delta in update.items():
            state.update(delta or {})
            if node == "understand" and state.get("qu") is not None:
                qu = state["qu"]
                yield (
                    "understanding",
                    api.AskUnderstanding(
                        neutral_query=qu.neutral_query,
                        removed_premises=qu.removed_premises,
                        language=qu.language,
                        intent=qu.intent,
                    ),
                )
            if node == "retrieve" and state.get("evidence") is not None and state["evidence"].articles:
                yield "evidence", evidence_event(state["evidence"])
                if "writing" not in sent_status:
                    sent_status.add("writing")
                    yield "status", api.AskStatus(step="writing", message="Writing a cited answer")
            progressed = (
                node == "understand" and state.get("qu") is not None and state["qu"].intent != "unsupported"
            ) or (node == "synthesize" and state.get("draft") is not None)
            if progressed and node in STATUS_BY_NODE and STATUS_BY_NODE[node][0] not in sent_status:
                step, msg = STATUS_BY_NODE[node]
                sent_status.add(step)
                yield "status", api.AskStatus(step=step, message=msg)
    outcome = state.get("outcome")
    if outcome in ("answer", "fallback"):
        ans = answer_event(session, state) if outcome == "answer" else fallback_event(state)  # type: ignore[arg-type]
        ans.articles = cited_articles(session, ans)
        yield "answer_final", ans
    else:
        yield "abstain", abstain_event(session, state)  # type: ignore[arg-type]


def ask_graph(session: Session, client: QdrantClient, embedder: Embedder) -> Any:
    retriever = make_retriever(session, client, embedder, lambda: datetime.now(UTC))
    g = load_yaml("guardrails.yaml")
    return build(structured, retriever, make_stored_summary(session), g["min_sources_for_bar"], g["sensitive_keywords"])
