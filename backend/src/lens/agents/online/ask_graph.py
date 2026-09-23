"""Ask graph (Graph 2, docs/06), linear chain first:

understand -> route -> retrieve (widen the window once if weak) -> synthesize (G-GEN-01, G-GEN-08,
G-IN-05) -> verify (G-GEN-03, retry synthesis with the unsupported sentences, max 2)
  -> answer | prune (keep only judge-supported sentences) | fallback (stored verified summary) | abstain

Nodes are pure functions of state plus injected dependencies: `llm` (lens.llm.client.structured),
`retriever` (query, window_days) -> Evidence, and `stored_summary` (story_ids) -> a published summary
or None. Synthesis gets no tools. User text and article text reach the model only inside delimiters.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Literal, TypedDict

from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel

from lens.agents.offline.evidence import EvidenceArticle, clean, render
from lens.agents.offline.story_graph import LLM, RETRY_NOTE
from lens.agents.prompts import skill, system_prompt
from lens.guardrails.base import GuardResult
from lens.guardrails.generation import check_citations, check_faithfulness, check_premises, check_scope
from lens.llm.client import LLMError
from lens.schemas.analysis import CitedSentence, FaithfulnessVerdict
from lens.schemas.ask import SECTIONS, AskDraft, QueryUnderstanding, cited_sections

MAX_VERIFIER_RETRIES = 2  # docs/06: bounded loops only
AbstainReason = Literal["insufficient_coverage", "out_of_scope", "service_unavailable"]


@dataclass(frozen=True)
class Evidence:
    articles: list[EvidenceArticle]  # balanced, refs A1..An in rank order
    story_ids: list[str]
    scope: str  # stories | global | none
    top_score: float
    closest_story_ids: list[str] = field(default_factory=list)


class AskState(TypedDict, total=False):
    raw_query: str
    qu: QueryUnderstanding | None
    evidence: Evidence | None
    retrieval_attempts: int
    windows: list[int]  # window_days per retrieval attempt (config retry.widen_window_days)
    draft: AskDraft | None
    verdict: FaithfulnessVerdict | None
    attempts: int
    feedback: str | None
    fallback: dict[str, Any] | None
    abstain_reason: AbstainReason | None
    outcome: Literal["answer", "fallback", "abstain"]
    guards: list[GuardResult]
    prompt_versions: dict[str, str]
    models: dict[str, dict[str, str]]
    errors: list[str]
    pruned: list[CitedSentence]


def question_block(qu: QueryUnderstanding) -> str:
    premises = "\n".join(f"- {clean(p)}" for p in qu.removed_premises) or "(none)"
    return f"<question>\n{clean(qu.neutral_query)}\n</question>\n<removed_premises>\n{premises}\n</removed_premises>"


def judge_lines(d: AskDraft) -> str:
    return "\n".join(
        f"- [{name}] {s.text} (cites {', '.join(s.citations)})" for name, sec in cited_sections(d).items() for s in sec
    )


def build(
    llm: LLM,
    retriever: Callable[[str, int], Evidence],
    stored_summary: Callable[[list[str]], dict[str, Any] | None],
) -> Any:
    def call(
        state: AskState,
        task: str,
        tier: str,
        model: type[BaseModel],
        system: tuple[str, str],
        user: str,
        exclude: set[str] | None = None,
    ) -> tuple[Any, dict[str, Any]]:
        meta: dict[str, str] = {}
        out = llm(
            tier,
            model,
            system[0],
            user,
            run_name=f"ask.{task}",
            prompt_version=system[1],
            tags=["graph:online"],
            exclude_families=exclude,
            meta=meta,
        )
        return out, {
            "prompt_versions": {**state.get("prompt_versions", {}), task: system[1]},
            "models": {**state.get("models", {}), task: meta},
        }

    def err(state: AskState, where: str, e: Exception) -> list[str]:
        return [*state.get("errors", []), f"{where}: {e}"]

    def understand(state: AskState) -> dict[str, Any]:
        s = skill("query_understanding")
        user = f"<question>\n{clean(state['raw_query'])}\n</question>"
        try:
            qu, rec = call(
                state,
                "query_understanding",
                "query_understanding",
                QueryUnderstanding,
                (s.text, f"query_understanding@{s.version}"),
                user,
            )
        except LLMError as e:
            # Never search with the raw (possibly loaded) phrasing: no understanding, no answer.
            return {"qu": None, "abstain_reason": "service_unavailable", "errors": err(state, "understand", e)}
        return {"qu": qu, **rec}

    def after_understand(state: AskState) -> str:
        qu = state.get("qu")
        if qu is None:
            return "abstain"
        if qu.intent == "unsupported":
            return "refuse"
        return "retrieve"

    def refuse(state: AskState) -> dict[str, Any]:
        return {"abstain_reason": "out_of_scope", "outcome": "abstain"}

    def retrieve(state: AskState) -> dict[str, Any]:
        qu = state["qu"]
        assert qu is not None
        n = state.get("retrieval_attempts", 0)
        windows = state["windows"]
        ev = retriever(qu.neutral_query, windows[min(n, len(windows) - 1)])
        return {"evidence": ev, "retrieval_attempts": n + 1}

    def after_retrieve(state: AskState) -> str:
        ev = state["evidence"]
        if ev is not None and ev.articles:
            return "synthesize"
        return "retrieve" if state["retrieval_attempts"] < len(state["windows"]) else "abstain"

    def synthesize(state: AskState) -> dict[str, Any]:
        qu, ev = state["qu"], state["evidence"]
        assert qu is not None and ev is not None
        attempts = state.get("attempts", 0) + 1
        fix = f"\n\n{RETRY_NOTE}\n{state['feedback']}" if state.get("feedback") else ""
        user = f"{question_block(qu)}\n\n{render(ev.articles)}{fix}"
        try:
            d, rec = call(state, "ask_synthesis", "synthesis", AskDraft, system_prompt("ask_synthesis"), user)
        except LLMError as e:
            return {"draft": None, "attempts": MAX_VERIFIER_RETRIES + 1, "errors": err(state, "synthesize", e)}
        refs = {a.ref for a in ev.articles}
        guards = [*state.get("guards", [])]
        cit = check_citations(cited_sections(d), refs)
        prem = check_premises(qu.removed_premises, [p.premise for p in d.premises])
        guards += [cit, prem]
        if not (cit.passed and prem.passed):
            why = [
                *cit.meta.get("sentences", []),
                *(f"premise not addressed: {p}" for p in prem.meta.get("missing", [])),
            ]
            return {"draft": None, "attempts": attempts, "feedback": "\n".join(why), "guards": guards, **rec}
        # G-GEN-08: drop sentences whose scope words contradict their own citations.
        scope = check_scope({k: getattr(d, k) for k in SECTIONS}, len(ev.articles))
        guards.append(scope)
        drop = set(scope.meta.get("drop", []))
        pruned = [*state.get("pruned", []), *(x for k in SECTIONS for x in getattr(d, k) if x.text in drop)]
        kept = d.model_copy(update={k: [x for x in getattr(d, k) if x.text not in drop] for k in SECTIONS})
        if not kept.tldr:
            feedback = "\n".join(f"{t} ({why})" for t, why in scope.meta["why"].items())
            return {
                "draft": None,
                "attempts": attempts,
                "feedback": feedback,
                "guards": guards,
                "pruned": pruned,
                **rec,
            }
        return {"draft": kept, "attempts": attempts, "feedback": None, "guards": guards, "pruned": pruned, **rec}

    def after_synthesize(state: AskState) -> str:
        if state.get("draft") is not None:
            return "verify"
        return "synthesize" if state.get("attempts", 0) <= MAX_VERIFIER_RETRIES else "fallback"

    def verify(state: AskState) -> dict[str, Any]:
        d, ev = state["draft"], state["evidence"]
        assert d is not None and ev is not None
        user = f"{render(ev.articles)}\n\nSentences to check:\n{judge_lines(d)}"
        writer = state.get("models", {}).get("ask_synthesis", {}).get("family")
        try:
            v, rec = call(
                state,
                "judge_faithfulness",
                "judge",
                FaithfulnessVerdict,
                system_prompt("judge_faithfulness"),
                user,
                exclude={writer} if writer else None,
            )
        except LLMError as e:
            return {"verdict": None, "errors": err(state, "verify", e)}  # unverified is never shown
        res = check_faithfulness(v)
        feedback = None if res.passed else "\n".join(v.unsupported_sentences)
        return {"verdict": v, "feedback": feedback, "guards": [*state.get("guards", []), res], **rec}

    def after_verify(state: AskState) -> str:
        v = state.get("verdict")
        if v is None:
            return "fallback"
        if v.verdict == "pass" and not v.unsupported_sentences:
            return "answer"
        return "synthesize" if state.get("attempts", 0) <= MAX_VERIFIER_RETRIES else "prune"

    def prune(state: AskState) -> dict[str, Any]:
        """G-GEN-03 fallback: keep only sentences the judge did not flag (all were checked)."""
        d, v = state["draft"], state["verdict"]
        assert d is not None and v is not None

        def ok(x: CitedSentence) -> bool:
            return not any(x.text.strip() in f for f in v.unsupported_sentences)

        kept = d.model_copy(
            update={
                **{k: [x for x in getattr(d, k) if ok(x)] for k in SECTIONS},
                "premises": [
                    p
                    if p.evidence_says is None or ok(p.evidence_says)
                    else p.model_copy(update={"evidence_says": None})
                    for p in d.premises
                ],
            }
        )
        removed = [x for sec in cited_sections(d).values() for x in sec if not ok(x)]
        return {"draft": kept if kept.tldr else None, "pruned": [*state.get("pruned", []), *removed]}

    def after_prune(state: AskState) -> str:
        return "answer" if state.get("draft") is not None else "fallback"

    def answer(state: AskState) -> dict[str, Any]:
        return {"outcome": "answer"}

    def fallback(state: AskState) -> dict[str, Any]:
        """docs/06 fallback_precomputed: the stored, already-verified story summary, else abstain."""
        ev = state.get("evidence")
        stored = stored_summary(ev.story_ids) if ev else None
        if stored is not None:
            return {"fallback": stored, "outcome": "fallback"}
        return {"abstain_reason": state.get("abstain_reason") or "insufficient_coverage", "outcome": "abstain"}

    def abstain(state: AskState) -> dict[str, Any]:
        return {"abstain_reason": state.get("abstain_reason") or "insufficient_coverage", "outcome": "abstain"}

    g = StateGraph(AskState)
    for name, fn in (
        ("understand", understand),
        ("refuse", refuse),
        ("retrieve", retrieve),
        ("synthesize", synthesize),
        ("verify", verify),
        ("prune", prune),
        ("answer", answer),
        ("fallback", fallback),
        ("abstain", abstain),
    ):
        g.add_node(name, fn)
    g.add_edge(START, "understand")
    g.add_conditional_edges("understand", after_understand, ["retrieve", "refuse", "abstain"])
    g.add_conditional_edges("retrieve", after_retrieve, ["synthesize", "retrieve", "abstain"])
    g.add_conditional_edges("synthesize", after_synthesize, ["verify", "synthesize", "fallback"])
    g.add_conditional_edges("verify", after_verify, ["answer", "synthesize", "prune", "fallback"])
    g.add_conditional_edges("prune", after_prune, ["answer", "fallback"])
    for end in ("refuse", "answer", "fallback", "abstain"):
        g.add_edge(end, END)
    return g.compile(name="ask")
