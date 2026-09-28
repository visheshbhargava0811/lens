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
from lens.core.settings import get_settings
from lens.db.checkpoint import ask_checkpointer
from lens.db.models import Article, AskTurn, Chunk, GuardEvent, LicenseMode, Source, Story, User
from lens.factchecks.match import lookup as factcheck_lookup
from lens.factchecks.match import max_similarity
from lens.guardrails.pii import mask, mask_any
from lens.llm.client import structured
from lens.memory import store as memory
from lens.nlp.embed import Embedder
from lens.ops import kill
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
    story_fact_checks,
    visible_story,
)
from lens.stats.coverage import BIAS_BUCKETS, bucket, rated_share_confidence

ABSTAIN_MESSAGES = {  # docs/10 copy
    "insufficient_coverage": "There isn't enough reliable coverage to answer this yet. "
    "Here are the closest stories we found.",
    "out_of_scope": "Lens covers news reporting. Try asking what outlets have reported about a story.",
    "service_unavailable": "Lens can't answer right now. Please try again in a few minutes.",
    "guard_block": "Lens can't answer this question.",
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
            for a, s in session.execute(
                select(Article, Source)
                .join(Source)
                .where(Article.id.in_(ids), Article.id.not_in(kill.taken_down_articles(ids)))  # G-OPS-03
            )
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


def initial_state(query: str, ui_lang: str | None = None, previous: list[str] | None = None) -> AskState:
    windows = load_yaml("retrieval.yaml")["retry"]["widen_window_days"]
    return {
        "raw_query": query,
        "ui_lang": ui_lang,
        "windows": list(windows),
        "guards": [],
        "errors": [],
        "pruned": [],
        "previous_questions": previous or [],
    }


def previous_questions(session: Session, session_id: str | None, n: int) -> list[str]:
    """docs/11 working memory: the session's last `n` neutral questions (topics, never answers or news claims),
    oldest first. Follow-ups are re-neutralized and re-retrieved; nothing is answered from a past answer."""
    try:
        sid = uuid.UUID(session_id or "")
    except ValueError:
        return []
    rows = session.execute(
        select(AskTurn.neutral_query)
        .where(AskTurn.session_id == sid, AskTurn.neutral_query.is_not(None))
        .order_by(AskTurn.created_at.desc())
        .limit(n)
    ).scalars()
    return [q for q in rows if q][::-1]


# Limitations are written by code, so they are templates per language, not model output.
LIMITS = {
    "en": {
        "premise": "None of the retrieved articles report that {premise}.",
        "limited": "Limited coverage: this answer draws on {n} outlet(s).",
        "global": "No single story matched the question closely; this answer draws on related coverage.",
        "pruned": "Some sentences were removed because they could not be verified against their sources.",
        "stale": "Latest report we found is from {hours} hours ago.",
        "language": "We couldn't tell which language you wrote in, so this answer is in English.",
        "translation": "The {language} translation couldn't be checked, so this answer is in English.",
        "snippets": "Based on headlines and short feed summaries, not full articles.",
    },
    "hi": {
        "premise": "जो लेख मिले, उनमें से किसी ने यह रिपोर्ट नहीं किया कि {premise}।",
        "limited": "सीमित कवरेज: यह जवाब {n} माध्यम(ओं) पर आधारित है।",
        "global": "कोई एक स्टोरी सवाल से सीधे मेल नहीं खाई; यह जवाब इससे जुड़े कवरेज पर आधारित है।",
        "pruned": "कुछ वाक्य हटा दिए गए क्योंकि उन्हें उनके स्रोतों से जाँचा नहीं जा सका।",
        "stale": "हमें मिली सबसे ताज़ा रिपोर्ट {hours} घंटे पुरानी है।",
        "language": "हम पहचान नहीं सके कि आपने किस भाषा में लिखा, इसलिए यह जवाब अंग्रेज़ी में है।",
        "translation": "{language} अनुवाद की जाँच नहीं हो सकी, इसलिए यह जवाब अंग्रेज़ी में है।",
        "snippets": "सुर्ख़ियों और छोटे फ़ीड सारांशों पर आधारित, पूरे लेखों पर नहीं।",
    },
    # Marathi (Phase 8): awaiting a native-speaker review, like the Hindi copy (STATUS open items).
    "mr": {
        "premise": "मिळालेल्या कोणत्याही लेखात {premise} असे नोंदवलेले नाही.",
        "limited": "मर्यादित कव्हरेज: हे उत्तर {n} माध्यमांवर आधारित आहे.",
        "global": "प्रश्नाशी थेट जुळणारी एकही बातमी मिळाली नाही; हे उत्तर संबंधित कव्हरेजवर आधारित आहे.",
        "pruned": "काही वाक्ये काढून टाकली, कारण ती त्यांच्या स्रोतांशी पडताळता आली नाहीत.",
        "stale": "आम्हाला मिळालेली सर्वात ताजी बातमी {hours} तासांपूर्वीची आहे.",
        "language": "तुम्ही कोणत्या भाषेत लिहिले ते ओळखता आले नाही, म्हणून हे उत्तर इंग्रजीत आहे.",
        "translation": "{language} अनुवादाची पडताळणी होऊ शकली नाही, म्हणून हे उत्तर इंग्रजीत आहे.",
        "snippets": "मथळे आणि छोट्या फीड सारांशांवर आधारित, पूर्ण लेखांवर नाही.",
    },
}
LANGUAGE_NAMES = {"hi": "Hindi", "mr": "Marathi"}


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


def evidence_event(ev: Evidence, stale: bool = False) -> api.AskEvidence:
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
        stale=stale,
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


def merge_fact_checks(state: AskState, story_checks: list[api.FactCheckRef], limit: int = 6) -> list[api.FactCheckRef]:
    """Fact-checks of the reader's own claim first, then those matched to the stories used; no duplicates."""
    out: dict[str, api.FactCheckRef] = {}
    for f in [*(api.FactCheckRef(**x) for x in state.get("fact_checks") or []), *story_checks]:
        out.setdefault(f.url, f)
    return sorted(out.values(), key=lambda f: f.match != "same_claim")[:limit]


def answer_event(session: Session, state: AskState) -> api.AskAnswer:
    ev, d, qu = state["evidence"], state["draft"], state["qu"]
    assert ev is not None and d is not None and qu is not None
    by_ref = {a.ref: a for a in ev.articles}
    found = [p.evidence_says for p in d.premises if p.evidence_says is not None]
    sections = [_stored_shape(getattr(d, k), by_ref) for k in SECTIONS] + [_stored_shape(found, by_ref)]
    ids = sorted({c["article_id"] for sec in sections for s in sec for c in s["citations"]})
    tldr, what, agree, disagree, premises = cited_api(sections, _chunk_of(session, ids))

    g = load_yaml("guardrails.yaml")
    lang = state.get("lang") or "en"
    L = LIMITS.get(lang, LIMITS["en"])
    guards = state.get("guards", [])
    limitations = [L["premise"].format(premise=p.premise.rstrip(".")) for p in d.premises if p.evidence_says is None]
    n_sources = len({a.article.source_id for a in ev.articles})
    if n_sources < g["min_sources_for_bar"]:
        limitations.append(L["limited"].format(n=n_sources))
    if ev.scope == "global":
        limitations.append(L["global"])
    if state.get("pruned"):
        limitations.append(L["pruned"])
    fresh = next((x for x in reversed(guards) if x.guard_id == "G-EV-04"), None)
    if fresh is not None and fresh.meta.get("stale") and "newest_hours" in fresh.meta:
        limitations.append(L["stale"].format(hours=round(fresh.meta["newest_hours"])))
    if any(x.guard_id == "G-IN-04" and not x.passed for x in guards):
        limitations.append(L["language"])
    if any(x.guard_id == "G-OUT-06" and not x.passed for x in guards):
        wanted = (state.get("ui_lang") or "")[:2] or (qu.language if qu else "")
        limitations.append(L["translation"].format(language=LANGUAGE_NAMES.get(wanted, "Hindi")))
    limitations.append(L["snippets"])
    return api.AskAnswer(
        basis="live",
        lang=lang,
        tldr=tldr,
        what_happened=what[:2] if state.get("summary_length") == "short" else what,  # format only (docs/11)
        agreements=agree,
        disagreements=disagree,
        premises_addressed=premises,
        limitations=limitations,
        follow_up_questions=d.follow_up_questions[:3],
        coverage=evidence_coverage(ev),
        fact_checks=merge_fact_checks(state, story_fact_checks(session, [uuid.UUID(i) for i in ev.story_ids])),
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
        lang=s.lang,
        tldr=s.sentences[:1],
        what_happened=s.sentences[1:],
        agreements=s.agreements,
        disagreements=s.disagreements,
        premises_addressed=[],
        limitations=limitations,
        follow_up_questions=[],
        coverage=detail.story.coverage,
        fact_checks=merge_fact_checks(state, detail.fact_checks),
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


def record_turn(
    session: Session,
    state: dict[str, Any],
    query: str,
    session_id: str | None,
    final: BaseModel | None,
    latency_ms: int,
    turn_id: uuid.UUID | None = None,
) -> AskTurn:
    """G-OPS-04 audit trail: one ask_turns row per question and its guard events. The query and every
    free-text field are PII-masked before storage (G-OUT-05); rows are purged after `retention_days`."""
    try:
        sid = uuid.UUID(session_id or "")
    except ValueError:
        sid = uuid.uuid4()
    qu, ev, v = state.get("qu"), state.get("evidence"), state.get("verdict")
    outcome = state.get("outcome") or "error"
    tid = turn_id or uuid.uuid4()
    turn = AskTurn(
        id=tid,
        session_id=sid,
        raw_query=mask(query)[0],
        neutral_query=mask(qu.neutral_query)[0] if qu else None,
        lang=qu.language if qu else None,
        intent=qu.intent if qu else None,
        story_ids=[uuid.UUID(i) for i in ev.story_ids] if ev else None,
        answer=mask_any(final.model_dump(mode="json")) if final is not None else None,
        abstained=outcome == "abstain",
        outcome=outcome,
        abstain_reason=state.get("abstain_reason"),
        evidence_article_ids=[a.article.article_id for a in ev.articles] if ev else None,
        verifier=mask_any(v.model_dump()) if v is not None else None,
        errors=mask_any(state.get("errors") or []),
        model_versions={**(state.get("models") or {}), "tokens": state.get("tokens") or {}},
        prompt_versions=state.get("prompt_versions"),
        langsmith_run_id=str(tid) if turn_id and get_settings().langsmith_tracing else None,
        latency_ms=latency_ms,
    )
    session.add(turn)
    session.flush()
    for g in state.get("guards", []):
        session.add(
            GuardEvent(
                run_id=g.run_id or f"ask:{turn.id}",
                guard_id=g.guard_id,
                stage="ask",
                passed=g.passed,
                action=g.action,
                reason=mask(g.reason)[0],
                score=g.score,
                meta=mask_any({"ask_turn_id": str(turn.id), **g.meta}),
            )
        )
    session.flush()
    return turn


def purge_ask_turns(session: Session, now: datetime, checkpointer: Any = None) -> int:
    """docs/03 retention (DPDP): delete Ask turns, their guard events and their checkpoint threads
    (thread_id == turn id) after `ask.retention_days`."""
    from datetime import timedelta

    from sqlalchemy import delete

    cutoff = now - timedelta(days=load_yaml("guardrails.yaml")["ask"]["retention_days"])
    if checkpointer is not None:
        for tid in session.execute(select(AskTurn.id).where(AskTurn.created_at < cutoff)).scalars():
            checkpointer.delete_thread(str(tid))
    session.execute(delete(GuardEvent).where(GuardEvent.stage == "ask", GuardEvent.created_at < cutoff))
    return session.execute(delete(AskTurn).where(AskTurn.created_at < cutoff)).rowcount  # type: ignore[attr-defined, no-any-return]


def ask_events(
    session: Session,
    query: str,
    graph: Any,
    session_id: str | None = None,
    ui_lang: str | None = None,
    user: User | None = None,
) -> Iterator[tuple[str, BaseModel]]:
    """Runs the graph and yields (event, payload) for SSE. Only verified answers are ever sent.
    Records the turn (audit trail) before the final event; the caller commits."""
    import time

    t0 = time.monotonic()
    turn_id = uuid.uuid4()  # also the checkpoint thread id, so an audit row leads to its checkpoints
    # The turn id is also the LangSmith root run id, so audit rows link to traces (online evals, docs/08).
    config = {"configurable": {"thread_id": str(turn_id)}, "run_id": turn_id}
    yield "status", api.AskStatus(step="understanding", message="Understanding the question")
    # docs/11: memory changes output language and format only, never retrieval, outlets or stances.
    prefs = memory.preferences(session, user) if user is not None and user.consent_at is not None else {}
    lang = prefs.get("output_language") or ui_lang
    turns = memory.cfg()["working_memory_turns"]
    state: dict[str, Any] = dict(initial_state(query, lang, previous_questions(session, session_id, turns)))
    state["summary_length"] = prefs.get("summary_length", "standard")
    sent_status: set[str] = set()
    if kill.generation(session).off:  # G-OPS-03 global: no live generation; story pages keep their summaries
        state.update({"outcome": "abstain", "abstain_reason": "service_unavailable"})
    for update in [] if state.get("outcome") else graph.stream(state, config, stream_mode="updates"):
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
                yield "evidence", evidence_event(state["evidence"], bool(state.get("stale")))
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
    final: api.AskAnswer | api.AskAbstain
    if outcome in ("answer", "fallback"):
        final = answer_event(session, state) if outcome == "answer" else fallback_event(state)  # type: ignore[arg-type]
        final.articles = cited_articles(session, final)
    else:
        final = abstain_event(session, state)  # type: ignore[arg-type]
    turn = record_turn(session, state, query, session_id, final, int((time.monotonic() - t0) * 1000), turn_id)
    if user is not None and user.consent_at is not None:
        turn.user_id = user.id  # Ask history in /me (consent only)
    yield ("answer_final" if isinstance(final, api.AskAnswer) else "abstain"), final


def ask_graph(
    session: Session,
    client: QdrantClient,
    embedder: Embedder,
    *,
    checkpoint: bool = True,
    wrap_retriever: Callable[[Callable[[str, int], Evidence]], Callable[[str, int], Evidence]] | None = None,
) -> Any:
    """The production Ask graph. `wrap_retriever` lets evals plant evidence (adversarial set)."""
    retriever = make_retriever(session, client, embedder, lambda: datetime.now(UTC))
    if wrap_retriever is not None:
        retriever = wrap_retriever(retriever)
    fcfg = load_yaml("retrieval.yaml")["freshness"]

    def freshness() -> dict[str, Any]:
        from dataclasses import asdict

        from lens.pipeline.freshness import refresh

        return asdict(refresh(client, embedder, fcfg))

    g = load_yaml("guardrails.yaml")
    return build(
        structured,
        retriever,
        make_stored_summary(session),
        g["min_sources_for_bar"],
        g["sensitive_keywords"],
        g["ask"]["min_language_confidence"],
        {"terms": g["attribution"]["allegation_terms"], "markers": g["attribution"]["markers"]},
        freshness,
        fcfg["stale_hours"],
        checkpointer=ask_checkpointer() if checkpoint else None,
        judge_retries=g["ask"]["max_judge_retries"],
        loaded_terms=g["attribution"]["allegation_terms"],
        factcheck_lookup=lambda qu: factcheck_lookup(
            session,
            client,
            embedder,
            structured,
            [*qu.removed_premises, *([qu.neutral_query] if qu.intent == "fact_check" else [])],
        ),
        similarity=lambda texts, claims: max_similarity(embedder, texts, claims),
        false_balance_threshold=g["false_balance"]["min_similarity"],
        languages=tuple(g["localization"]["languages"]),
        translation_check=g["translation_check"],  # skip_words, phrase_words, aliases
        generation_allowed=lambda story_ids: kill.generation_allowed(session, story_ids),
    )
